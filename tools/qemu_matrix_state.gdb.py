"""Observe the exact shared module; optional commands only write the QEMU menu-driver mailbox."""
import gdb,json,os
context=json.load(open(os.environ['MIRROR_MATRIX_CONTEXT']))
gdb.execute('source '+context['observer'])
table=gdb.parse_and_eval('module_list')
rows=[table[i] for i in range(table.type.range()[1]+1) if table[i]['name'].string()=='mirror']
if len(rows)==1 and rows[0]['status'].string()=='OK' and not int(rows[0]['error']):
    row=rows[0]
    text=int(row['info']['init'])-context['init_offset']
    bss=int(row['config'][0]['ref']['value'])-context['active_offset']
    gdb.execute('add-symbol-file '+context['debug']+' '+hex(text)+' -s .bss '+hex(bss))
    preview=gdb.parse_and_eval("'fx_camera.c'::camera.report")
    gate=gdb.parse_and_eval("'mirror_capture_gate.c'::gate.r")
    state={'preview':{key:int(preview[key]) for key in ('running','frames','discarded','error','allocated','native_capture')},
        'gate':{key:int(gate[key]) for key in ('phase','error','installed','latched','patch_done')},
        'vram':{'address':int(gdb.parse_and_eval('vram_lv.vram')),'width':int(gdb.parse_and_eval('vram_lv.width')),
                'height':int(gdb.parse_and_eval('vram_lv.height')),'pitch':int(gdb.parse_and_eval('vram_lv.pitch'))}}
    print('MIRROR_MATRIX_STATE='+json.dumps(state,sort_keys=True))
ctl=[table[i] for i in range(table.type.range()[1]+1) if table[i]['name'].string()=='mxctl']
if len(ctl)==1 and ctl[0]['status'].string()=='OK':
    print('MIRROR_MATRIX_CONTROL='+json.dumps({key:int(ctl[0]['config'][i]['ref']['value'].dereference()) for key,i in
        (('result',1),('completed',2),('fixture_phase',3),('fixture_layouts',4),('fixture_checked',5),('fixture_free',6),('fixture_allocator',7),('fixture_delivery_checks',8),('menu_status',9),('raw_cases',10),('raw_checked',11),('raw_negative',12))}))
if context.get('action'):
    reply=gdb.execute('maintenance packet qqemu.sstepbits',to_string=True)
    assert all(s in reply for s in ('ENABLE=','NOIRQ=','NOTIMER=')),'QEMU extension required'
    assert len(ctl)==1 and ctl[0]['status'].string()=='OK' and not int(ctl[0]['error'])
    assert context['action'] in (1,2,3,4)
    addr=int(ctl[0]['config'][0]['ref']['value'])
    gdb.execute('set {unsigned int}'+hex(addr)+' = '+str(0x4d570000+context['action']))
    print('MIRROR_MATRIX_COMMAND='+str(context['action']))
