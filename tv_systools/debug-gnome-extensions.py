from pydbus import SessionBus
from readchar import readkey
from tqdm import tqdm

bus = SessionBus()
shell = bus.get('org.gnome.Shell', '/org/gnome/Shell')
extensions = shell.ListExtensions()
enabled = [uuid for uuid, attrs in extensions.items() if attrs['state'] == 1]
evil = []

print("Should I disable all extensions first? ", end='', flush=True)
disable_all = readkey() in "yY"

if disable_all:
    for uuid in tqdm(enabled, desc='Disabling extensions', unit=' extension'):
        shell.DisableExtension(uuid)

for uuid in enabled:
    print(extensions[uuid]['name'], end=' ')
    if disable_all:
        shell.EnableExtension(uuid)
        print('has been enabled.\n(m)ark evil / (d)isable and continue / leave on and (c)ontinue / (q)uit ', end='', flush=True)
    else:
        shell.DisableExtension(uuid)
        print('has been disabled.\n(m)ark evil / (e)nable and continue / leave off and (c)ontinue / (q)uit', end='', flush=True)
    answer = readkey()

    if answer in 'mM':
        evil.append(uuid)
        if disable_all:
            shell.DisableExtension(uuid)
            print('evil, disabled')
        else:
            print('left disabled')
    elif answer in 'dD':
        shell.DisableExtension(uuid)
        print('disabled')
    elif answer in 'eE':
        shell.EnableExtension(uuid)
        print('enabled')
    elif answer in 'cC':
        print('.')
    elif answer in 'qQ':
        if not disable_all:
            shell.EnableExtension(uuid)
            print('enabled, quitting')
        else:
            print('quitting')
        break

print('The following extensions have been identified as evil:', ", ".join(extensions[uuid]['name'] for uuid in evil))
if disable_all:
    for uuid in tqdm(set(enabled) - set(evil), desc='Enabling remaining extensions', unit=' ext.'):
        shell.EnableExtension(uuid)
