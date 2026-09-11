import os, pathlib, shutil, subprocess, sys, tempfile
repo=pathlib.Path.cwd()
with tempfile.TemporaryDirectory(prefix='v231-test-') as temp:
    root=pathlib.Path(temp); copy=root/'repo'
    subprocess.run(['git','clone','--quiet','--no-hardlinks',str(repo),str(copy)],check=True)
    for rel in ['hermes-dev-v2','tests/hermes_autopilot']:
        shutil.copytree(repo/rel,copy/rel,dirs_exist_ok=True)
    argv=['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','1000','--gid','1000','--cap-drop','ALL']
    for name in ['bin','lib','lib64','share']:
        if pathlib.Path('/usr',name).exists(): argv+=['--ro-bind','/usr/'+name,'/usr/'+name]
    argv+=['--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home/test','--bind',str(copy),'/repo','--chdir','/repo','--clearenv','--setenv','HOME','/home/test','--setenv','PATH','/usr/bin:/bin','--setenv','PYTHONDONTWRITEBYTECODE','1']
    result=subprocess.run(argv+sys.argv[1:]);sys.exit(result.returncode)
