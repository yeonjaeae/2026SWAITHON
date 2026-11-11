from pathlib import Path
import os
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]

def test_compose_has_one_published_port():
    data=yaml.safe_load((ROOT/'compose.yaml').read_text())
    published={k:v['ports'] for k,v in data['services'].items() if 'ports' in v}
    assert list(published)==['gateway']
    assert len(published['gateway'])==1
    assert data['services']['candidate']['environment']['AI_BASE_URL']=='http://ai:8000'
    assert 'recommendations:/data' in data['services']['candidate']['volumes']

def test_compose_targets_and_dependencies_exist():
    doc=yaml.safe_load((ROOT/'compose.yaml').read_text())
    dockerfile=(ROOT/'Dockerfile').read_text()
    for name,service in doc['services'].items():
        assert 'AS '+service['build']['target'] in dockerfile
        assert all(dep in doc['services'] for dep in service.get('depends_on',{}))

def test_setup_env_does_not_overwrite_or_print_key(tmp_path):
    script=tmp_path/'setup_env.py';script.write_text((ROOT/'setup_env.py').read_text())
    first=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,check=True)
    data=(tmp_path/'.env').read_text()
    key=next(x.split('=',1)[1] for x in data.splitlines() if x.startswith('SERVICE_API_KEY='))
    assert len(key)>=32 and key not in first.stdout
    subprocess.run([sys.executable,str(script)],capture_output=True,text=True,check=True)
    assert (tmp_path/'.env').read_text()==data
    if os.name=='posix':assert (tmp_path/'.env').stat().st_mode & 0o777 == 0o600
