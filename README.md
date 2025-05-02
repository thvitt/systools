## Small System Tools

This repository is intended for small scripts and utilities that do not fit anywhere else. Scripts marked with † are not in active use and maintenance.

Python scripts reside in python submodules in `tv_systools`. All other scripts live in `scripts`. The easiest way to install everything is probably using pipx or uv tools:

- `pipx install git+https://github.com/thvitt/systools` or
- `uv tools install git+https://github.com/thvitt/systools`

| Script                 | Description                                                              | More             | Kind   |
| ---------------------- | -----------------------------------------------------------------------  | ---------------- | ------ |
| apt-describe-update    | Show info about last apt updates                                         | `--help`         | Python |
| choice                 | Randomly select from input lines                                         |                  | Python |
| clean-sync-conflicts   | Remove sync-conflicts files as they are created from Syncthing           |                  | Python |
| debug-gnome-extensions | find a gnome extension that does sth bad                                 |                  | Python |
| extract-mw-backup      | extract pages from a MediaWiki backup file                               | --help           | Python |
| fetch-and-link         | Move file and replace with symlink                                       | `--help`         | Python |
| glyphinfo              | Show info abut the glyphs of a font                                      | `--help`         | Python |
| git-cor                | Synchronously checkout submodules                                        | `git cor --help` | Shell  |
| hcopy, hpaste          | Copy/Paste markdown as html                                              |                  | Shell  |
| j                      | Add a new entry to the LogSeq journal                                    |                  | Python |
| json2toml              | simple json to toml converter                                            |                  | Python |
| keyboard-overview      | Current keyboard map                                                     |                  | Shell  |
| linked-assets          | ZIP or copy a HTML file with all local files linked from there           | --help           | Python |
| monitor-switch         | Switch screen configurations using rofi                                  |                  | Python |
| nco                    | NextCloud Open (in browser)                                              | not configurable | Python |
| pipxtouvtools          | generate a script with `uv tool install` commands for current pipx setup |                  | Python |
| pmvn                   | Run Maven in the nearest ancestor directory with a POM                   |                  | Shell  |
| public-link            | _very_ specific tool to create a public link for a file in my nectcloud  |                  | Python |
| ssh-exit-multiplex     | Exit multiplexed ssh connections                                         | (below)          | Shell  |
| vpn                    | Wrapper for `nm-cli` to switch VPN connections                           | `--help`         | Shell  |
| wacom-config           | Auto-configure Wacom screen                                              |                  | Python |
| wh                     | show information about a command’s source                                |                  | Python |
| mimecorrtype           | Autodetects and fixes e-mail attachment MIME types                       | †                | Perl   |
| mw2confluence          | MediaWiki to Confluence wiki ASCII syntax                                | †                | Perl   |

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
