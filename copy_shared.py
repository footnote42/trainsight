import os
import shutil

def sync_dir(src, dst, ignore_patterns=None):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*(ignore_patterns or [])))

ignore_list = ['.venv', '__pycache__', '*.pyc', 'audit.log', 'results', '.git']

# Sync for challenger (both root and nested to cover all resolution paths)
sync_dir('src', 'app/challenger/src', ignore_list)
sync_dir('config', 'app/challenger/config', ignore_list)
sync_dir('data', 'app/challenger/data', ignore_list)

sync_dir('src', 'app/challenger/app/src', ignore_list)
sync_dir('config', 'app/challenger/app/config', ignore_list)
sync_dir('data', 'app/challenger/app/data', ignore_list)

# Sync for briefing (both root and nested to cover all resolution paths)
sync_dir('src', 'app/briefing/src', ignore_list)
sync_dir('config', 'app/briefing/config', ignore_list)
sync_dir('data', 'app/briefing/data', ignore_list)

sync_dir('src', 'app/briefing/app/src', ignore_list)
sync_dir('config', 'app/briefing/app/config', ignore_list)
sync_dir('data', 'app/briefing/app/data', ignore_list)

print("Shared directories synced successfully into agent root and app folders.")
