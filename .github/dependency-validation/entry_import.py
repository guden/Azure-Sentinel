import ast,importlib.util,os,socket,sys,types
from pathlib import Path
root=Path(sys.argv[1]);folder=Path(sys.argv[2]);entry=sys.argv[3]
# Populate only literal required settings, using synthetic local test values.
for path in (root/folder).rglob('*.py'):
 for n in ast.walk(ast.parse(path.read_text())):
  if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Attribute) and isinstance(n.value.value,ast.Name) and n.value.value.id=='os' and n.value.attr=='environ' and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,str):
   os.environ[n.slice.value]='local-test'
os.environ['AzureWebJobsStorage']='DefaultEndpointsProtocol=http;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net'
os.environ['AWS_REGION_NAME']='us-east-1'
os.environ['GCP_CREDENTIALS_FILE_CONTENT']='{}'
def forbid(*args,**kwargs):raise RuntimeError('Unexpected network connection during import')
socket.socket.connect=forbid
package=types.ModuleType('entry_probe');package.__path__=[str(root/folder)];sys.modules['entry_probe']=package
name='entry_probe' if entry=='__init__.py' else 'entry_probe.main'
spec=importlib.util.spec_from_file_location(name,root/folder/entry,submodule_search_locations=[str(root/folder)] if entry=='__init__.py' else None)
m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
assert callable(m.main)
print('ENTRY IMPORT PASS')
