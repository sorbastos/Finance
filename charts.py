"""Gráficos locais em canvas, sem dependências ou dados externos."""
from datetime import date, timedelta

PALETTE=['#008b86','#7952c7','#ffab19','#2fa6df','#ef6356','#7897ba']


def money(value):
    return 'R$ '+f'{value/100:,.2f}'.replace(',','_').replace('.',',').replace('_','.')


def grouped(data, limit=5):
    items=sorted(((k,v) for k,v in data.items() if v>0),key=lambda r:r[1],reverse=True)
    if len(items)>limit:
        items=items[:limit-1]+[('Demais itens',sum(v for _,v in items[limit-1:]))]
    return items


def daily(data):
    if not data: return []
    start,end=date.fromisoformat(min(data)),date.fromisoformat(max(data))
    return [((start+timedelta(days=i)).isoformat(),data.get((start+timedelta(days=i)).isoformat(),0)) for i in range((end-start).days+1)]


def draw(canvas, data, title, mode):
    dark=getattr(canvas,'dark_theme',False)
    foreground='#e5edf7' if dark else '#35485d'
    muted='#a8b7c9' if dark else '#7c899b'
    surface='#1e293b' if dark else 'white'
    grid='#334155' if dark else '#edf2f8'
    canvas.delete('all')
    w,h=canvas.winfo_width(),canvas.winfo_height()
    if w<30 or h<80:return
    def text(x,y,label,**kw):
        canvas.create_text(x,y,text=label,fill=kw.pop('fill',foreground),font=kw.pop('font',('DejaVu Sans',10)),**kw)
    text(22,26,title,anchor='w',font=('DejaVu Sans',11,'bold'))
    if not data or not sum(data.values()):
        text(w/2,h/2,'Nenhum movimento neste recorte.\nEscolha outro período ou importe um extrato.',justify='center',width=w-44,fill=muted)
        return
    total=sum(data.values())
    if mode=='Evolução':
        points=daily(data);maximum=max(v for _,v in points)
        left,right,top,bottom=65,w-24,66,h-46
        for fraction in (0,.5,1):
            y=bottom-(bottom-top)*fraction
            canvas.create_line(left,y,right,y,fill=grid)
            text(left-8,y,money(round(maximum*fraction)),anchor='e',font=('DejaVu Sans',8))
        coords=[]
        for i,(_,v) in enumerate(points):
            x=(left+right)/2 if len(points)==1 else left+(right-left)*i/(len(points)-1)
            y=bottom-(bottom-top)*v/maximum
            coords.extend((x,y))
        if len(coords)>2:canvas.create_line(*coords,fill=PALETTE[0],width=2)
        if len(points)<=32:
            for x,y in zip(coords[::2],coords[1::2]):canvas.create_oval(x-3,y-3,x+3,y+3,fill=PALETTE[0],outline='')
        text(left,h-24,points[0][0],anchor='w',font=('DejaVu Sans',8))
        if len(points)>1:text(right,h-24,points[-1][0],anchor='e',font=('DejaVu Sans',8))
        text(w-24,48,'Total '+money(total),anchor='e',fill=muted,font=('DejaVu Sans',9))
        return
    limit=max(1,min(5,(h-65)//44))
    items=grouped(data,limit)
    if mode=='Rosca':
        diameter=min(h-90,w*.42)
        if diameter<60:return
        x0,y0=20,65
        start=90
        for i,(name,value) in enumerate(items):
            extent=value/total*360
            if len(items)==1:canvas.create_oval(x0,y0,x0+diameter,y0+diameter,fill=PALETTE[i],outline='')
            else:canvas.create_arc(x0,y0,x0+diameter,y0+diameter,start=start,extent=-extent,fill=PALETTE[i],outline=surface,width=2)
            start-=extent
        inset=diameter*.24
        canvas.create_oval(x0+inset,y0+inset,x0+diameter-inset,y0+diameter-inset,fill=surface,outline='')
        text(x0+diameter/2,y0+diameter/2,'100%',font=('DejaVu Sans',15,'bold'))
        x=diameter+42
        for i,(name,value) in enumerate(items):
            y=78+i*44
            canvas.create_oval(x,y-4,x+7,y+3,fill=PALETTE[i],outline='')
            label=name if len(name)<23 else name[:21]+'…'
            text(x+14,y,label,anchor='w',font=('DejaVu Sans',9))
            text(x+14,y+17,f'{money(value)}  ·  {value/total:.0%}',anchor='w',font=('DejaVu Sans',8),fill=muted)
        return
    maximum=max(v for _,v in items)
    for i,(name,value) in enumerate(items):
        y=64+i*44
        label=name if len(name)<=26 else name[:24]+'…'
        text(22,y,label,anchor='w',font=('DejaVu Sans',9))
        text(w-22,y,money(value),anchor='e',font=('DejaVu Sans',9,'bold'))
        canvas.create_rectangle(22,y+12,w-22,y+20,fill=grid,outline='')
        canvas.create_rectangle(22,y+12,22+(w-44)*value/maximum,y+20,fill=PALETTE[i],outline='')
