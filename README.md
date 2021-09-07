## Small System Tools

This repository is intended for small scripts and utilities that do not require installation except for just copying them into `$PATH`. Scripts marked with † are not in active use and maintenance. 

| Script             | Description                                            | More             |
|--------------------|--------------------------------------------------------|------------------|
| choose             | Randomly select from input lines                       |                  |
| fetch-and-link     | Move file and replace with symlink                     | `--help`         |
| git-cor            | Synchronously checkout submodules                      | `git cor --help` |
| keyboard-overview  | Current keyboard map                                   |                  |
| pmvn               | Run Maven in the nearest ancestor directory with a POM |                  |
| ssh-exit-multiplex | Exit multiplexed ssh connections                       | (below)          |
| vpn                | Wrapper for `nm-cli` to switch VPN connections         | `--help`         |
| wacom-config       | Auto-configure Wacom screen                            |                  |
| mimecorrtype       | Autodetects and fixes e-mail attachment MIME types     | †                |
| mw2confluence      | MediaWiki to Confluence wiki ASCII syntax              | †                |



### ssh-exit-multiplex

Expects multiplex configuration like the following in `~/.ssh/config`:

```
Host *
    ControlPath  ~/.ssh/control-%r@%h:%p
    ControlMaster auto
    ControlPersist 30s
```

In certain circumstances (suspend etc.), these connections may become stale, causing all _future_ ssh connections to the relevant hosts to hang. This command simply looks for the control files and asks ssh to exit the connections. I run this on every resume via a systemd user service:

```systemd
[Unit]
Description=Exits multiplex ssh connections on resume
After=suspend.target

[Service]
Type=oneshot
ExecStart=%h/bin/ssh-exit-multiplex

[Install]
WantedBy=suspend.target
```
