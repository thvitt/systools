## Small System Tools

This repository is intended for small scripts and utilities that do not fit anywhere else. Scripts marked with † are not in active use and maintenance.

Python scripts reside in python submodules in `tv_systools`. They can usually also be used by copying the python script file and making it executable if you have their respective dependencies installed globally. All other scripts live in `scripts` and can just be copied to some bin directory.

You can use pipx to install everything including python dependencies.

| Script                 | Description                                              | More               | Kind   |
| --------------------   | -------------------------------------------------------- | ------------------ | ----   |
| apt-describe-update    | Show info about last apt updates                         | `--help`           | Python |
| choice                 | Randomly select from input lines                         |                    | Python |
| debug-gnome-extensions | find a gnome extension that does sth bad                 |                    | Python |
| fetch-and-link         | Move file and replace with symlink                       | `--help`           | Python |
| glyphinfo              | Show info abut the glyphs of a font                      | `--help`           | Python |
| git-cor                | Synchronously checkout submodules                        | `git cor --help`   | Shell  |
| hcopy, hpaste          | Copy/Paste markdown as html                              |                    | Shell  |
| j                      | Add a new entry to the LogSeq journal                    |                    | Python |
| keyboard-overview      | Current keyboard map                                     |                    | Shell  |
| monitor-switch         | Switch screen configurations using rofi                  |                    | Python |
| nco                    | NextCloud Open (in browser)                              | not configurable   | Python |
| pmvn                   | Run Maven in the nearest ancestor directory with a POM   |                    | Shell  |
| ssh-exit-multiplex     | Exit multiplexed ssh connections                         | (below)            | Shell  |
| vpn                    | Wrapper for `nm-cli` to switch VPN connections           | `--help`           | Shell  |
| wacom-config           | Auto-configure Wacom screen                              |                    | Python |
| mimecorrtype           | Autodetects and fixes e-mail attachment MIME types       | †                  | Perl   |
| mw2confluence          | MediaWiki to Confluence wiki ASCII syntax                | †                  | Perl   |

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
