"""Private Windows font measurement, with selected sfnt tables pinned to file."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import struct
import sys


def font_faces(path):
    raw=Path(path).read_bytes()
    if len(raw)<12:raise ValueError('invalid sfnt font')
    offsets=[0]
    if raw[:4]==b'ttcf':
        n=struct.unpack_from('>I',raw,8)[0]
        if not 0<n<100:raise ValueError('invalid font collection')
        offsets=list(struct.unpack_from('>'+str(n)+'I',raw,12))
    faces=[]
    try:
        for offset in offsets:
            n=struct.unpack_from('>H',raw,offset+4)[0];tables={}
            for i in range(n):
                tag,_,start,size=struct.unpack_from('>4sIII',raw,offset+12+i*16)
                if start+size>len(raw):raise ValueError('truncated font table')
                tables[tag]=raw[start:start+size]
            name=tables[b'name'];_,count,base=struct.unpack_from('>HHH',name,0);names=set()
            for i in range(count):
                platform,encoding,language,kind,size,start=struct.unpack_from('>HHHHHH',name,6+i*12)
                if kind in (1,4,6,16) and platform in (0,3):
                    names.add(name[base+start:base+start+size].decode('utf-16-be'))
            faces.append((names,tables))
    except (KeyError,struct.error,UnicodeError) as exc:raise ValueError('invalid font tables') from exc
    return faces


class PrivateFont:
    def __init__(self,path,name,size):
        self.path=Path(path);self.name=name;self.size=size
        self.dc=self.font=self.old=None;self.loaded=False;self.closed=True

    def __enter__(self):
        if sys.platform!='win32':raise ValueError('private font verification requires Windows GDI')
        faces=font_faces(self.path)
        self.matches=[t for names,t in faces if self.name.casefold() in {s.casefold() for s in names}]
        aliases={s.casefold() for names,t in faces if t in self.matches for s in names}
        if not self.matches:raise ValueError('font file does not contain requested face')
        self.gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        definitions={
            'AddFontResourceExW':([w.LPCWSTR,w.DWORD,ctypes.c_void_p],ctypes.c_int),
            'RemoveFontResourceExW':([w.LPCWSTR,w.DWORD,ctypes.c_void_p],w.BOOL),
            'CreateCompatibleDC':([ctypes.c_void_p],ctypes.c_void_p),
            'CreateFontW':([ctypes.c_int]*5+[w.DWORD]*8+[w.LPCWSTR],ctypes.c_void_p),
            'SelectObject':([ctypes.c_void_p,ctypes.c_void_p],ctypes.c_void_p),
            'DeleteObject':([ctypes.c_void_p],w.BOOL),
            'DeleteDC':([ctypes.c_void_p],w.BOOL),
            'GetTextFaceW':([ctypes.c_void_p,ctypes.c_int,w.LPWSTR],ctypes.c_int),
            'GetFontData':([ctypes.c_void_p,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD],w.DWORD),
            'GetGlyphIndicesW':([ctypes.c_void_p,w.LPCWSTR,ctypes.c_int,ctypes.POINTER(w.WORD),w.DWORD],w.DWORD),
            'GetTextExtentPoint32W':([ctypes.c_void_p,w.LPCWSTR,ctypes.c_int,ctypes.c_void_p],w.BOOL),
        }
        for name,(args,result) in definitions.items():
            fn=getattr(self.gdi,name);fn.argtypes=args;fn.restype=result
        try:
            self.loaded=bool(self.gdi.AddFontResourceExW(str(self.path),0x10,None))
            if not self.loaded:raise ValueError('private font loading failed')
            self.dc=self.gdi.CreateCompatibleDC(None)
            self.font=self.gdi.CreateFontW(-self.size,0,0,0,400,0,0,0,1,0,0,4,0,self.name)
            if not self.dc or not self.font:raise ValueError('font/DC allocation failed')
            self.old=self.gdi.SelectObject(self.dc,self.font)
            buf=ctypes.create_unicode_buffer(256)
            if not self.gdi.GetTextFaceW(self.dc,256,buf):raise ValueError('selected font unknown')
            self.selected_face=buf.value
            if self.selected_face.casefold() not in aliases:raise ValueError('GDI substituted requested font: '+self.selected_face)
            self.face=self.name
            actual={}
            for tag in (b'name',b'cmap',b'maxp'):
                table=int.from_bytes(tag,'little');n=self.gdi.GetFontData(self.dc,table,0,None,0)
                if n==0xffffffff or n>100_000_000:raise ValueError('GDI sfnt table unavailable')
                raw=ctypes.create_string_buffer(n)
                if self.gdi.GetFontData(self.dc,table,0,raw,n)!=n:raise ValueError('GDI font data unavailable')
                actual[tag]=raw.raw
            if not any(all(t.get(k)==v for k,v in actual.items()) for t in self.matches):raise ValueError('selected GDI tables differ from font file')
            self.closed=False
            return self
        except BaseException:
            self.close();raise

    def measure(self,text):
        if self.closed:raise ValueError('font is closed')
        if not text:return 0
        length=len(text.encode('utf-16-le'))//2
        glyphs=(w.WORD*length)()
        if self.gdi.GetGlyphIndicesW(self.dc,text,length,glyphs,1)==0xffffffff or any(x==0xffff for x in glyphs):raise ValueError('requested font lacks original-text glyph')
        size=(w.LONG*2)()
        if not self.gdi.GetTextExtentPoint32W(self.dc,text,length,size):raise ValueError('font measurement failed')
        return size[0]

    def close(self):
        if self.dc and self.old:self.gdi.SelectObject(self.dc,self.old)
        if self.font:self.gdi.DeleteObject(self.font)
        if self.dc:self.gdi.DeleteDC(self.dc)
        if self.loaded:self.gdi.RemoveFontResourceExW(str(self.path),0x10,None)
        self.dc=self.font=self.old=None;self.loaded=False;self.closed=True

    def __exit__(self,*args):self.close()
