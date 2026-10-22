"""Offline connector compatibility probes; run in each connector's isolated environment.

These tests use loopback HTTP or fake SDK responses, never production credentials.
They are not substitutes for Azure Functions staging validation.
"""
import argparse
import ast
import asyncio
import base64
import datetime
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
ASYNC = {
    'cloudflare': 'Solutions/Cloudflare/Data Connectors/AzureFunctionCloudflare',
    'crowdstrike': 'Solutions/CrowdStrike Falcon Endpoint Protection/Data Connectors/CrowdstrikeReplicator/CrowdstrikeFalconAPISentinelConnector',
    'gcp': 'Solutions/Google Cloud Platform Cloud Monitoring/Data Connectors/AzureFunctionGCPMonitor',
    'prisma': 'Solutions/PaloAltoPrismaCloud/Data Connectors/AzureFunctionPrismaCloud',
    'rapid7': 'Solutions/Rapid7InsightVM/Data Connectors/InsightVMCloudAPISentinelConnector',
}


def load(path, name='probe'):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def test_async(name):
    import aiohttp
    from aiohttp import web
    if name == 'crowdstrike':
        from aiobotocore.session import get_session
        from gzip_stream import AsyncGZIPDecompressedStream
        # Exercise the SDK's aiohttp transport creation without contacting AWS.
        async with get_session().create_client('s3', region_name='us-east-1',
                aws_access_key_id='test', aws_secret_access_key='test') as client:
            assert callable(client.get_object)
    elif name == 'gcp':
        from google.cloud.monitoring_v3.services.metric_service import MetricServiceAsyncClient
    if name == 'cloudflare':
        from azure.storage.blob.aio import BlobServiceClient
    else:
        from azure.storage.fileshare import ShareClient
    module = load(ASYNC[name] + '/sentinel_connector_async.py')
    received = []
    secret = b'local-test-key'
    async def handler(request):
        raw = await request.text()
        signed = 'POST\n{}\napplication/json\nx-ms-date:{}\n/api/logs'.format(
            len(raw), request.headers['x-ms-date'])
        expected = base64.b64encode(hmac.new(secret, signed.encode(), hashlib.sha256).digest()).decode()
        assert request.headers['Authorization'] == 'SharedKey test:' + expected
        assert request.headers['Log-Type'] == 'CompatibilityTest'
        assert request.query['api-version'] == '2016-04-01'
        received.extend(json.loads(raw))
        return web.Response(status=200)
    app = web.Application()
    app.router.add_post('/api/logs', handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            args = [session, f'http://127.0.0.1:{port}', 'test', base64.b64encode(secret).decode()]
            if name != 'rapid7':
                args.append('CompatibilityTest')
            connector = module.AzureSentinelConnectorAsync(*args)
            events = [{'id': 1}, {'id': 2}]
            if name == 'rapid7':
                await connector.send_events(events, 'CompatibilityTest')
            else:
                for event in events:
                    await connector.send(event)
                await connector.flush()
            assert received == events
            assert connector.successfull_sent_events_number == 2
            if hasattr(connector, "failed_sent_events_number"):
                assert connector.failed_sent_events_number == 0
    finally:
        await runner.cleanup()


def test_box():
    from boxsdk.auth.jwt_auth import JWTAuth
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import jwt
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())
    auth = JWTAuth(client_id='test-client', client_secret='test-secret', enterprise_id='123',
                   jwt_key_id='test-key', rsa_private_key_data=pem)
    captured = {}
    def authenticate(data, **kwargs):
        captured.update(data)
        return 'test-access-token'
    auth.send_token_request = authenticate
    auth.authenticate_instance()
    assertion = captured['assertion']
    claims = jwt.decode(assertion, key.public_key(), algorithms=['RS256'],
                        audience='https://api.box.com/oauth2/token')
    assert claims['sub'] == '123'
    assert claims['iss'] == 'test-client'


def test_trend():
    import jwt
    # Execute the actual pure helper without importing its cloud configuration.
    path = ROOT / 'Solutions/Trend Micro Vision One/Data Connectors/AzureFunctionTrendMicroXDR/shared_code/utils.py'
    tree = ast.parse(path.read_text())
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('get_clp_id', 'find_token_by_clp')]
    ns = {'jwt': jwt}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(path), 'exec'), ns)
    token = jwt.encode({'cid': 'tenant-test', 'sub': 123, 'exp': 1}, 'local-test-secret'*3, algorithm='HS256')
    assert ns['get_clp_id'](token) == 'tenant-test'
    assert ns['find_token_by_clp']('tenant-test', [token]) == token
    assert ns['find_token_by_clp']('absent', [token]) is None


def test_snowflake():
    import snowflake.connector
    from snowflake.connector import DictCursor
    directory = 'Solutions/Snowflake/Data Connectors/AzureFunctionSnowflake'
    package = types.ModuleType('snowflake_probe')
    package.__path__ = [str(ROOT / directory)]
    sys.modules['snowflake_probe'] = package
    for key in ('SNOWFLAKE_ACCOUNT', 'SNOWFLAKE_USER', 'SNOWFLAKE_PASSWORD', 'WORKSPACE_ID', 'SHARED_KEY', 'AzureWebJobsStorage'):
        os.environ[key] = 'local-test'
    module = load(directory + '/main.py', 'snowflake_probe.main')
    timestamp = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    for fn, field, table in [('get_login_events','EVENT_TIMESTAMP','LOGIN_HISTORY'),
                              ('get_reader_login_events','EVENT_TIMESTAMP','LOGIN_HISTORY'),
                              ('get_query_events','START_TIME','QUERY_HISTORY'),
                              ('get_reader_query_events','START_TIME','QUERY_HISTORY')]:
        cursor = Mock()
        cursor.__iter__ = Mock(return_value=iter([{field: timestamp}]))
        connection = Mock()
        connection.cursor.return_value = cursor
        rows = list(getattr(module, fn)(connection, timestamp))
        connection.cursor.assert_called_once_with(DictCursor)
        assert rows[0][field] == timestamp.isoformat()
        assert rows[0]['source_table'] == table
        assert cursor.execute.call_count == 2
        cursor.close.assert_called_once()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('connector', choices=[*ASYNC, 'box', 'trend', 'snowflake'])
    name = parser.parse_args().connector
    if name in ASYNC:
        asyncio.run(test_async(name))
    else:
        globals()['test_' + name]()
    print(name + ': PASS (offline probe only)')
