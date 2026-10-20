"""Self-contained project folders with relative FITS paths and verified assets."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def file_digest(path, cancel=None):
    from .archive_catalog import check_cancel
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            check_cancel(cancel);digest.update(chunk)
    return digest.hexdigest()


def map_project_paths(state, mapper):
    """Only known file fields are paths; URLs, keys and target names stay intact."""
    result=deepcopy(state)
    for key in ('red','green','blue'):
        if result.get(key):result[key]=mapper(result[key])
    visited=set()
    def records(value):
        if id(value) in visited:return
        visited.add(id(value))
        if isinstance(value,dict):
            for key,item in list(value.items()):
                if key=='local_path' and item:value[key]=mapper(item)
                elif key=='aligned_paths' and isinstance(item,list):value[key]=[mapper(p) for p in item if p]
                elif isinstance(item,(dict,list)):records(item)
        elif isinstance(value,list):
            for item in value:records(item)
    records(result.get('image_wizard',{}))
    records(result.get('archive_provenance',{}))
    return result


def export_portable_project(state, destination, cancel=None, progress=lambda text:None):
    from .archive_catalog import check_cancel
    destination=Path(destination).resolve()
    parent=destination.parent
    if not parent.is_dir():raise ValueError('Choose an existing parent folder.')
    if destination.exists():raise FileExistsError('The portable project folder already exists; choose a new name.')
    files={}
    def collect(value):
        path=Path(value).resolve()
        if not path.is_file():raise FileNotFoundError(f'Missing referenced file: {path.name}. Restore or download it before exporting.')
        if not path.name.lower().endswith(('.fits','.fits.gz','.fit','.fts')):
            raise ValueError(f'Expected a FITS image reference: {path.name}')
        files[os.path.normcase(str(path))]=path
        return value
    map_project_paths(state,collect)
    if not files:raise ValueError('This project has no local FITS images to package. Download or compose images first.')
    # The temporary directory is created inside, and verified against, the chosen parent.
    with tempfile.TemporaryDirectory(prefix='.hubble-bundle-',dir=parent) as temp:
        staging=Path(temp).resolve()
        if not staging.is_relative_to(parent):raise ValueError('Invalid bundle staging path.')
        (staging/'data').mkdir();(staging/'results').mkdir()
        mappings={};manifest=[]
        for index,(identity,path) in enumerate(files.items(),start=1):
            check_cancel(cancel)
            safe=re.sub(r'[^A-Za-z0-9._-]+','_',path.name)[-120:]
            relative=f'data/{index:04d}_{safe}'
            digest=hashlib.sha256();size=0
            progress(f'Packaging image {index}/{len(files)}: {path.name}')
            with path.open('rb') as source,(staging/relative).open('wb') as target:
                for chunk in iter(lambda:source.read(1024*1024),b''):
                    check_cancel(cancel);target.write(chunk);digest.update(chunk);size+=len(chunk)
            mappings[identity]=relative
            manifest.append({'path':relative,'bytes':size,'sha256':digest.hexdigest()})
        portable=map_project_paths(state,lambda p:mappings[os.path.normcase(str(Path(p).resolve()))])
        if portable.get('archive_provenance'):
            portable['archive_provenance']['run_directory']='results'
        portable['portable_bundle']={'version':1,'manifest':'manifest.json'}
        (staging/'project.json').write_text(json.dumps(portable,indent=2),encoding='utf-8')
        (staging/'manifest.json').write_text(json.dumps({'version':1,'files':manifest},indent=2),encoding='utf-8')
        (staging/'README.txt').write_text('Move or copy this entire folder. Open project.json in Hubble Workbench.\nKeep data/ and manifest.json with the project. Images are verified when opening.\nresults/ is for subsequent previews; original source images were not modified.\n',encoding='utf-8')
        check_cancel(cancel)
        # Rename only the newly created, verified staging directory; never overwrite a project.
        if destination.exists():raise FileExistsError('Destination was created during export; choose another name.')
        staging.rename(destination)
    return destination/'project.json'


def load_project_document(path, cancel=None, progress=lambda text:None):
    from .archive_catalog import check_cancel
    path=Path(path).resolve();base=path.parent
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict):raise ValueError('Project JSON must contain an object.')
    bundle=data.get('portable_bundle')
    verified=set()
    def inside(value):
        relative=Path(value)
        if relative.is_absolute():raise ValueError('Portable project paths must be relative.')
        candidate=(base/relative).resolve()
        if not candidate.is_relative_to(base):raise ValueError('Portable project references a file outside its folder.')
        return candidate
    if bundle:
        if bundle.get('version')!=1 or bundle.get('manifest')!='manifest.json':raise ValueError('Unsupported portable project format.')
        manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('version')!=1:raise ValueError('Unsupported bundle manifest.')
        entries=manifest.get('files',[])
        for index,entry in enumerate(entries,start=1):
            check_cancel(cancel);asset=inside(entry['path'])
            progress(f'Verifying bundled image {index}/{len(entries)}: {asset.name}')
            if not asset.is_file() or asset.stat().st_size!=entry['bytes'] or file_digest(asset,cancel)!=entry['sha256']:
                raise ValueError(f'Bundled image is missing or changed: {entry["path"]}')
            verified.add(asset)
    def resolve(value):
        asset=inside(value) if bundle else (base/Path(value)).resolve()
        if bundle and asset not in verified:raise ValueError('A referenced image is absent from the bundle manifest.')
        return str(asset)
    result=map_project_paths(data,resolve)
    provenance=result.get('archive_provenance') or {}
    if provenance.get('run_directory'):
        directory=inside(provenance['run_directory']) if bundle else (base/Path(provenance['run_directory'])).resolve()
        provenance['run_directory']=str(directory)
    result.pop('portable_bundle',None)
    return result


def portable_folder_name(target):
    name=re.sub(r'[^A-Za-z0-9_-]+','_',str(target)).strip('_')[:50] or 'project'
    return 'Hubble_'+name+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')
