#!/usr/bin/env python3

__author__="Thorsten Vitt <tv@thorstenvitt.de>"
__version__="0.2"

import argparse
import logging
import sys
from os import fspath
from os.path import relpath
from pathlib import Path
from shutil import move
from typing import Optional, Union, Tuple

try:
    from ruyaml import YAML
    yaml = YAML()
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)

# Monkey-patch older Path implementations
if not hasattr(Path, 'readlink'):
    from os import readlink
    def _readlink(path):
        return Path(readlink(fspath(path)))
    Path.readlink = _readlink


class CannotLinkError(IOError): 
    ...


def fetch_and_link(src: Path, dst: Optional[Path] = None, *, absolute_symlink=False) -> Tuple[Path, Path]:
    """
    Moves src to dst and replaces src with a symlink to dst.
    
    This function is intended as a file move operation which leaves a "compatibility symlink" at src instead of removing src completely.

    Args:
        src: an existing file or directory that should be moved.
        dst: either the target filename or the target directory, if missing, the current directory is assumed. If dst is an existing directory, src's file name will be kept.

    Returns:
        (src, dst): normalized tuple of source and destination paths (i.e. (new link, new link target))
        
    Raises:
        CannotLinkError: if src already is a link that either points to dst or is relative (and thus cannot be moved)
    """

    # Argument normalization
    src = Path(src)
    if dst is None:
        dst = Path()
    else:
        dst = Path(dst)
    if dst.is_dir():
        dst /= src.name
        
    # Calculate the actual value for the future symlink at src
    if absolute_symlink:
        link_target = src.absolute()
    else:
        link_target = relpath(dst.resolve(), start=src.resolve().parent)

    # Sanity checks
    if src.is_symlink():
        if dst.exists() and src.resolve().samefile(dst) or src.resolve() == dst.resolve():
            raise CannotLinkError(f'{src} already is a symlink that points to {dst}, maybe try --reverse?')
        elif not src.readlink().is_absolute():
            raise CannotLinkError(f'{src} is a relative symlink, it would break when moving to {dst}, refusing.')  # [TODO] maybe rewrite?

    # Now do what we promised ...
    move(src, dst)
    src.symlink_to(link_target)
    logger.info('Moved %s to %s, symlink from %s to %s', src, dst, src, link_target)
    assert src.resolve().samefile(dst)
    return src, dst
    

def reverse_link(link: Union[str, Path], *, absolute_symlink=False):
    """
    Reads the given symbolic link and swaps it with the file linked to.

    Afterwards, link will be replaced with the file originally linked to (the target) 
    and the target will be a symlink to link.

    Args:
        link: a symbolic link
        absolute_symlink: if True, the new link will use an absolute path. Defaults to False.
        
    Returns:
        (new link, new link target)

    Raises:
        CannotLinkError: if no operation could be taken, e.g., because link is not actually a symbolic link
    """
    link = Path(link)
    if not link.is_symlink():
        raise CannotLinkError(f'{link} is not a symbolic link: cannot reverse, skipping.')
    link_target = (link.parent / link.readlink()).resolve()
    link.unlink()
    logger.debug('Removed link %s (to %s)', link, link_target)
    return fetch_and_link(link_target, link, absolute_symlink=absolute_symlink)


def getargs(argv=sys.argv[1:]):
    p = argparse.ArgumentParser(description="""Moves files and replaces them with a symlink to their new destination""")
    p.add_argument('src', nargs='*', help="Source file(s) or directorie(s)")
    p.add_argument('dst', help="""Destination file or directory. If missing and only one source given, assume current directory.
                   If more than one src is given, this must be a directory. If ending with /, assume a directory.""")
    p.add_argument('-p', '--parents', action='store_true', default=False, help="create parent directories if missing")
    p.add_argument('-a', '--absolute-link', action='store_true', default=False, help="symlink will be absolute")
    p.add_argument('-r', '--reverse', action='store_true', default=False, help="""
                   Reverse operation. If present, each file is assumed to be a symlink. The symlink is resolved, then
                   replaced with its target and the target is moved to the original symlink's place.
                   """)
    p.add_argument('-v', '--verbose', action='count', default=0, help="increase verbosity")
    p.add_argument('-V', '--version', action='version', version=f'%(prog)s {__version__}')
    if yaml is not None:
        p.add_argument('-d', '--dotbot', action='store_true', default=False, 
                       help="also add link option to dotbot config file (only forward)")
    options = p.parse_args(argv)

    logging.getLogger().setLevel(logging.WARNING - 10*options.verbose)
    
    # only 1 argument => move arg to ., but arg will be in dst => fix it
    if len(options.src) == 0:
        options.src.append(options.dst)
        options.dst = '.'
    
    return options


def forward_magic(options):
    assert not options.reverse
    
    dst = Path(options.dst)
    srcs = map(Path, options.src)
    
    if options.parents and not dst.absolute().parent.is_directory():
        dst.absolute().parent.mkdir(parents=True)
    if options.dst[-1] == '/':
        if dst.exists() and not dst.is_dir():
            logger.error('Destination %s exists but is not a directory', dst)
            sys.exit(-1)
        else:
            dst.mkdir(exist_ok=True)
            
    links = []
    for src in srcs:
        try:
            link, target = fetch_and_link(src, dst, absolute_symlink=options.absolute_link)
            links.append((link, target))
        except CannotLinkError as e:
            logger.error(str(e))

    if yaml and options.dotbot and links:
        to_dotbot(links)
        

def to_dotbot(links):
    with open('install.conf.yaml') as f:
        cfg = yaml.load(f)
    link_cfgs = [entry for entry in cfg if isinstance(entry, dict) and 'link' in entry.keys()]
    if link_cfgs:
        link_cfg = link_cfgs[0]['link']
    else:
        link_cfg = dict()
        cfg.append({'link': link_cfg})
        
    for source, target in links:
        if source in link_cfg:
            logger.warning('Dotbot link config for %s already present (%s), not adding link to %s', source, link_cfg[source], target)
        else:
            link_cfg[semantic_path(source)] = semantic_path(target)
            logger.debug('Dotbot: Adding link config %s: %s', source, target)
    with open('install.conf.yaml', 'w') as f:
        yaml.dump(cfg, f)
        logger.info('Updated dotbot link config')


def semantic_path(path: Path) -> str:
    if not isinstance(path, Path):
        path = Path(path)
    if path.is_absolute():
        try:
            return fspath(path.relative_to(Path().absolute()))
        except ValueError:
            try:
                return fspath('~' / path.relative_to(Path.home()))
            except ValueError:
                return fspath(path)
    else:
        if path.parts and path.parts[0] == '..':
            return semantic_path(path.absolute())
        else:
            return fspath(path)


def reverse_magic(options):
    assert options.reverse
    if options.dst and options.dst != '.':
        options.src.append(options.dst)

    for src in options.src:
        try:
            link = Path(src)
            reverse_link(link, absolute_symlink=options.absolute_link)
        except CannotLinkError as e:
            logger.error(str(e))
        
    
def main():
    logging.basicConfig(format='%(levelname)s: %(message)s')
    options = getargs()
    if options.reverse:
        reverse_magic(options)
    else:
        forward_magic(options)


if __name__ == "__main__":
    main()
