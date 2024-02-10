#!/usr/bin/python3

from argparse import ArgumentParser
from subprocess import run
import re
import logging

logger = logging.getLogger(__name__)

try:
    from systemd.journal import JournalHandler

    journal_handler = JournalHandler()
    logging.root.addHandler(journal_handler)
except ImportError:
    journal_handler = logging.NullHandler()

try:
    import notify2
except ImportError:
    notify2 = None


def get_monitors():
    import gi
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk
    display = Gdk.Display.get_default()
    return [display.get_monitor(i) for i in range(display.get_n_monitors())]


def get_output_names(monitors=None):
    if monitors is None:
        monitors = get_monitors()
    return [monitor.get_model() for monitor in monitors]


def udev_monitor():
    from pyudev import Context, Monitor
    context = Context()
    monitor = Monitor.from_netlink(context)
    monitor.filter_by('usb')
    while dev := monitor.poll():
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Udev encountered %s (Vendor ID: %s, Model: %s, action: %s) %s',
                         dev, dev.get('ID_VENDOR_ID'), dev.get('ID_MODEL'),
                         dev.action, dict(dev.properties))
        if dev.get('ID_VENDOR_ID') == '056a' and 'Wacom' in dev.get('ID_MODEL', ''):
            configure_devices(trigger=dev)


def configure_devices(expect_failure=False, trigger=None):
    try:
        devices = get_input_devices()
        output = None
        if devices:
            output = get_target_monitor()
            for id, label in devices.items():
                logger.info(f'Mapping {label} to {output}')
                run(['xsetwacom', '--set', id, 'MapToOutput', output])
        elif not expect_failure:
            logger.warning('No wacom devices found.')
        notification(devices, output, trigger, expect_failure)
        return devices
    except Exception as e:
        logger.exception('Something went wrong configuring devices (expect failure: %s, trigger: %s)', expect_failure,
                         trigger)
        _do_notify('Wacom Config Error', str(e))


_notification = None


def _do_notify(summary, message: str = '', *, update=True, transient=False, _may_restart=False):
    if options.notify and notify2:
        global _notification
        try:
            if _notification is None:
                _notification = notify2.Notification(summary, message)
            else:
                _notification.update(summary, message)
            if transient:
                _notification.set_urgency(notify2.URGENCY_LOW)
                _notification.set_hint_byte('transient', True)
            _notification.show()
        except:
            logger.warning('Notification service died, restarting', exc_info=True)
            if _may_restart:
                _notification = None
                notify2.init("Wacom Device Configurations")
                _do_notify(summary, message, update=False, transient=transient, _may_restart=False)
            else:
                raise


def notification(devices, output, trigger, expect_failure, *, _may_restart=True):
    if options.notify and notify2:
        if devices:
            summary = f'Mapped {len(devices)} Wacom devices to {output}'
            body = f'Mapped <b>{", ".join(devices.values())}</b> to output <b>{output}</b>.'
            if trigger:
                body += f'\n\nTriggered by {trigger}'
        else:
            summary = f'No Wacom device found.'
            body = 'Could not map any devices.'
        if devices or not expect_failure:
            _do_notify(summary, body, transient=True)


def get_target_monitor():
    if options.output != 'auto':
        output = options.output
    else:
        monitors = get_monitors()
        wacom_targets = [m.get_model() for m in monitors if m.get_manufacturer() == 'WAC']
        if wacom_targets:
            output = wacom_targets[0]
            if len(wacom_targets) > 1:
                logger.warning(f"Detected more than one Wacom monitor: {', '.join(wacom_targets)} -- selected the 1st")
        else:
            output = monitors[-1].get_model()
            logger.warning(f"No Wacom device found -- selecting {output} since it's the last one")
    return output


def get_input_devices():
    proc = run(['xsetwacom', '--list', 'devices'], capture_output=True, text=True)
    devices = {id: label for (label, id) in
               re.findall(r'^([^\t]*?)\s*\tid: (\w+)\t.*\n', proc.stdout, re.MULTILINE)}
    return devices


def getargparser() -> ArgumentParser:
    parser = ArgumentParser(description='configures all wacom devices we found')
    parser.add_argument('-o', '--output', default='auto', help="map output to device")
    parser.add_argument('-m', '--monitor', action='store_true', default=False,
                        help="wait for a device to be connected, configure then")
    parser.add_argument('-n', '--notify', action='store_true', default=False,
                        help="show a desktop notification on successful config")
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="verbosity for displayed messages")
    parser.add_argument('-f', '--logfile', help="log to file, not only to output")
    parser.add_argument('-l', '--loglevel', default='INFO', help="Log level for the logfile (default: INFO)")
    return parser


def main():
    global options
    options = getargparser().parse_args()
    logging.basicConfig(level=min(0, logging.WARNING - (10 * options.verbose)))
    if options.logfile:
        filehandler = logging.FileHandler(options.logfile)
        filehandler.setLevel(options.loglevel)
        logger.addHandler(filehandler)
    if options.notify:
        if notify2:
            notify2.init("Wacom Device Configurations")
        else:
            logger.warning("Notification library (notify2) not available")
    configure_devices(expect_failure=True)
    if options.monitor:
        udev_monitor()


if __name__ == '__main__':
    main()
