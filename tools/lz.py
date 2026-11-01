def lz77(d,o):
    if d[o]!=0x10: return None
    size=d[o+1]|d[o+2]<<8|d[o+3]<<16
    out=bytearray(); p=o+4
    try:
        while len(out)<size:
            flags=d[p];p+=1
            for i in range(8):
                if len(out)>=size: break
                if flags&(0x80>>i):
                    b1,b2=d[p],d[p+1];p+=2
                    n=(b1>>4)+3; disp=((b1&15)<<8|b2)+1
                    if disp>len(out): return None
                    for _ in range(n): out.append(out[-disp])
                else:
                    out.append(d[p]);p+=1
    except IndexError: return None
    return bytes(out[:size]), p-o
