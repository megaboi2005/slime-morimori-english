import sys,struct
from capstone import *
d=open(sys.argv[1],'rb').read()
start=int(sys.argv[2],16); end=int(sys.argv[3],16)
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
for ins in md.disasm(d[start:end],0x08000000+start):
    extra=''
    if ins.mnemonic=='ldr' and 'pc' in ins.op_str:
        try:
            imm=int(ins.op_str.split('#')[1].rstrip(']'),16)
            a=((ins.address+4)&~3)+imm-0x08000000
            extra='  ; =0x%08x'%struct.unpack_from('<I',d,a)[0]
        except: pass
    print('%08x: %-8s %s%s'%(ins.address,ins.mnemonic,ins.op_str,extra))
