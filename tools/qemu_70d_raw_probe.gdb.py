"""Explicit QEMU-only controls for the unshipped m70raw research module.

Commands: m70raw-arm MODE EDGES WIDTH_DIVISOR HEIGHT_DIVISOR; m70raw-status.
Needs matching core ELF plus build/70d-native-probe/m70raw.debug.o types. Controls
the probe's mailbox; never writes sensor pixels or Canon CPU registers from GDB.
"""
import json
import gdb


def _probe():
    reply=gdb.execute('maintenance packet qqemu.sstepbits',to_string=True)
    if not all(word in reply for word in ('ENABLE=','NOIRQ=','NOTIMER=')):
        raise gdb.GdbError('QEMU extension missing; refusing research control')
    table=gdb.parse_and_eval('module_list')
    rows=[table[i] for i in range(table.type.range()[1]+1) if table[i]['name'].string()=='m70raw']
    if len(rows)!=1 or rows[0]['status'].string()!='OK' or not int(rows[0]['enabled']) or int(rows[0]['error']):
        raise gdb.GdbError('The unique m70raw probe must be loaded and enabled without errors')
    return rows[0]


def _report(row):
    address=int(row['config'][5]['ref']['value'].dereference())&0xffffffff
    if not 0x1000<=address<0x20000000:
        raise gdb.GdbError('Invalid module-owned report address')
    return gdb.Value(address).cast(gdb.lookup_type('m70_report').pointer()).dereference()


def _object(value):
    kind=value.type.strip_typedefs()
    if kind.code==gdb.TYPE_CODE_STRUCT:
        return {field.name:_object(value[field.name]) for field in kind.fields()}
    if kind.code==gdb.TYPE_CODE_ARRAY:
        return [_object(value[i]) for i in range(kind.range()[1]+1)]
    return int(value)&0xffffffff


class Status(gdb.Command):
    def __init__(self):super().__init__('m70raw-status',gdb.COMMAND_USER)
    def invoke(self,arg,tty):
        if arg.strip():raise gdb.GdbError('Usage: m70raw-status')
        gdb.write('M70RAW_STATE='+json.dumps(_object(_report(_probe())),sort_keys=True)+'\n')


class Arm(gdb.Command):
    def __init__(self):super().__init__('m70raw-arm',gdb.COMMAND_USER)
    def invoke(self,arg,tty):
        try:mode,edges,width,height=map(int,arg.split())
        except ValueError:raise gdb.GdbError('Usage: m70raw-arm MODE EDGES WIDTH_DIVISOR HEIGHT_DIVISOR')
        if mode not in (1,2) or edges not in (1,2,4,8,3,12,15) or not 2<=width<=6 or not 2<=height<=6:
            raise gdb.GdbError('Invalid mode or edge parameters')
        if ((edges&3)==3 and width==2) or ((edges&12)==12 and height==2):
            raise gdb.GdbError('Opposing edges require a divisor of at least 3')
        row=_probe();report=_report(row)
        if int(report['phase']) in (1,2) or int(gdb.parse_and_eval('lens_info.job_state')):
            raise gdb.GdbError('Probe/camera is busy')
        configs=row['config']
        for index,number in ((1,mode),(2,edges),(3,width),(4,height),(0,0x51454d55)):
            address=int(configs[index]['ref']['value'])&0xffffffff
            gdb.execute('set {unsigned int}'+hex(address)+' = '+str(number))
        gdb.write('Queued one explicitly armed virtual-camera probe; wait for phase 1 before Release.\n')


Status();Arm()
