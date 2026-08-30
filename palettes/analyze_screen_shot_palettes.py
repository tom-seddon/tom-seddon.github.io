#!/usr/bin/python3
import sys,os,os.path,argparse,zipfile,subprocess,tempfile,shutil,collections,concurrent.futures,contextlib,html,re,traceback,array,math,fnmatch
import png

##########################################################################
##########################################################################

g_verbose=False

def pv(msg):
    if g_verbose:
        sys.stdout.write(msg)
        sys.stdout.flush()

##########################################################################
##########################################################################

def fatal(msg):
    sys.stderr.write('FATAL: %s\n'%msg)
    sys.exit(1)

##########################################################################
##########################################################################

def rmtree(path):
    if os.path.isdir(path): shutil.rmtree(path)

##########################################################################
##########################################################################

def makedirs(path):
    try: os.makedirs(path)
    except FileExistsError:
        # ignore - probably a race condition with another job.
        pass

##########################################################################
##########################################################################

POPCOUNT=[]
for i in range(256):
    n=0
    for j in range(8):
        if (i&1<<j)!=0: n+=1
    POPCOUNT.append(n)

##########################################################################
##########################################################################
    
BBCColour=collections.namedtuple('BBCColour','name rgb rgb_str rgba frgb')

BBC_COLOURS=[]
for i,name in enumerate(['black',
                        'red',
                        'green',
                        'yellow',
                        'blue',
                        'magenta',
                        'cyan',
                        'white']):
    # rgb='%s%s%s'%('ff' if (i&1)!=0 else '00',
    #               'ff' if (i&2)!=0 else '00',
    #               'ff' if (i&4)!=0 else '00')
    frgb=(float((i&1)!=0),
          float((i&2)!=0),
          float((i&4)!=0))
    rgb=(int(frgb[0])*255,
         int(frgb[1])*255,
         int(frgb[2])*255)
    BBC_COLOURS.append(BBCColour(name=name,
                                 rgb=rgb,
                                 rgb_str='%02x%02x%02x'%(rgb[0],
                                                         rgb[1],
                                                         rgb[2]),
                                 rgba=(rgb[0],rgb[1],rgb[2],255),
                                 frgb=frgb))

##########################################################################
##########################################################################

# FOUR_COLOUR_PALETTE_INDEX[INDEX] - INDEX is an 8-bit value, with bit
# I set if BBC physical colour I is present in the image. If this is a
# 2 bpp palette, value is its index; otherwise, value is None.
FOUR_COLOUR_PALETTE_INDEX=[]

# FOUR_COLOUR_PALETTES[INDEX] - INDEX is the index of a 2 bpp palette.
# Value is a tuple (C0,C1,C2,C3), the 4 physical colours in the
# palette.
FOUR_COLOUR_PALETTES=[]

PALETTE_STRINGS=[]

for i in range(256):
    idxs=[]
    names=[]
    for bit in range(8):
        if (i&(1<<bit))!=0:
            idxs.append(bit)
            names.append(BBC_COLOURS[bit].name)
    if len(names)==0: names=['*invalid*']
    PALETTE_STRINGS.append('+'.join(names))

    if len(idxs)==4:
        FOUR_COLOUR_PALETTE_INDEX.append(len(FOUR_COLOUR_PALETTES))
        FOUR_COLOUR_PALETTES.append(tuple(idxs))
    else: FOUR_COLOUR_PALETTE_INDEX.append(None)
    del idxs

##########################################################################
##########################################################################

Image=collections.namedtuple('Image','png_path palette')

##########################################################################
##########################################################################

class HTMLElementContext:
    def __init__(self,f,name):
        self._f=f
        self._name=name

    def __enter__(self): return self

    def __exit__(self,exc_type,exc_value,traceback):
        if exc_type is None:
            if self._f is not None:
                self._f.write(f'''</{self._name}>''')

class HTMLWriter:
    def __init__(self,f):
        self._f=f

    def write(self,x): self._f.write(html.escape(str(x)))

    def el(self,name,attrs={},cond=True):
        assert name not in ['img'] # don't let me do a dumb
        
        if cond:
            self._el(name,attrs)
            return HTMLElementContext(self._f,name)
        else: return HTMLElementContext(None,None)

    def vel(self,name,attrs={},cond=True):
        if cond: self._el(name,attrs)

    def _el(self,name,attrs):
        assert isinstance(attrs,dict),type(attrs)
        
        for c in name: assert c.isalnum() # TODO: is this right???
        self._f.write(f'''<{name}''')
        for k,v in attrs.items():
            self._f.write(f''' {k}="{html.escape(str(v))}"''')
        self._f.write('>')

##########################################################################
##########################################################################

# Game=collections.namedtuple('Game','png_path id')
# GetGamePaletteResult=collections.namedtuple('GetGamePaletteResult','id palette')

##########################################################################
##########################################################################

# def get_game_palette(game):
#     reader=png.Reader(filename=game.png_path)
#     result=reader.asRGBA8()

#     palette=0

#     for row in result[2]:
#         assert len(row)==result[0]*4

#         if isinstance(row,bytearray):
#             for x in range(0,len(row),4):
#                 # palette|=1<<((row[x+0]>>7)|
#                 #              (row[x+1]>>6&2)|
#                 #              (row[x+2]>>5&4))

#                 pixel=0

#                 if row[x+0]>=128: pixel|=1
#                 if row[x+1]>=128: pixel|=2
#                 if row[x+2]>=128: pixel|=4

#                 palette|=1<<pixel
#         elif isinstance(row,list):
#             for x in range(0,len(row),4):
#                 r,g,b=row[x+0:x+3]
#                 assert r>=0 and r<256
#                 assert g>=0 and g<256
#                 assert b>=0 and b<256

#                 pixel=((0 if r<128 else 1)|
#                        (0 if g<128 else 2)|
#                        (0 if b<128 else 4))

#                 palette|=1<<pixel

#         else: assert False,type(row)

#     return GetGamePaletteResult(id=game.id,
#                                 palette=palette)

##########################################################################
##########################################################################

def write_palette_html(path,
                       title,
                       palette_indexes=None,
                       more_columns_fun=None):
    if palette_indexes is not None and len(palette_indexes)==0: return
    
    with open(path,'wt') as f:
        w=HTMLWriter(f)

        def w2(indexes):
            for index in indexes:
                with w.el('tr'):
                    with w.el('td'): w.write(index)
                    palette=FOUR_COLOUR_PALETTES[index]
                    for j in range(4):
                        colour=BBC_COLOURS[palette[j]]
                        with w.el('td',{'bgcolor':'#%s'%colour.rgb_str}):
                            with w.el('font',{'color':'#ffffff'},cond=palette[j] in (0,4,5)):
                                w.write(colour.name)
                    if more_columns_fun is not None:
                        more_columns_fun(w,index)

        with w.el('html'):
            with w.el('head'):
                with w.el('title'):
                    w.write(title)
            with w.el('body'):
                with w.el('table',{'border':1}):
                    if palette_indexes is None:
                        w2(range(len(FOUR_COLOUR_PALETTES)))
                    else:
                        w2(palette_indexes)

##########################################################################
##########################################################################

# class Game:
#     def __init__(self,image_path,id_):
#         self.png_path=png_path
#         self.id=id_
#         self.palette=None

# def find_games(options):
#     game_id_re=re.compile(r'''.*-(?P<id>[0-9]+)\.[^.]+''')
    
#     images_folder_path=os.path.join(options.output_path,'unzipped_images')
#     makedirs(images_folder_path)

#     game_by_id={}
#     with zipfile.ZipFile(options.input_path,'r') as zf:
#         infolist=list(zf.infolist())

#         for info in infolist:
#             if os.path.isabs(info.filename):
#                 fatal('zip file contains absolute path: %s'%info.filename)
                
#         for info_index,info in enumerate(infolist):
#             print(f'''#{info_index} ({len(infolist)}): {info.filename}''')
#             # data=zf.read(info.filename)

#             image_path=os.path.join(images_folder_path,info.filename)
#             makedirs(os.path.dirname(image_path))

#             ext=os.path.splitext(info.filename)[1].lower()

#             match=game_id_re.match(info.filename)
#             if match is None:
#                 fatal('unexpected image name: %s'%name)

#             game_id=int(match.group('id'))

#             if ext=='.png':
#                 if not os.path.isfile(image_path):
#                     with open(image_path,'wb') as f:
#                         f.write(zf.read(info.filename))

#                 png_path=image_path
#             elif ext=='.gif':
#                 # there's exactly 1 .gif, and "convert SRC DEST"
#                 # doesn't handle it, possibly because it looks like
#                 # it's an animated one.
#                 #
#                 # luckily, the game is mode 7 , so the screen grab is
#                 # irrelevant.
#                 continue
#             else:
#                 png_path=image_path+'.png'
#                 if not os.path.isfile(png_path):
#                     with tempfile.NamedTemporaryFile(mode='wb',
#                                                      delete=False,
#                                                      suffix=ext) as img_f:
#                         img_f.write(zf.read(info.filename))
#                         img_f.close()

#                         result=subprocess.run(['convert',
#                                                img_f.name,
#                                                png_path],
#                                               check=True)
                        
#                     os.unlink(img_f.name)

#             assert game_id not in game_by_id
#             game_by_id[game_id]=Game(png_path,game_id)

#     return game_by_id

##########################################################################
##########################################################################

def unzip_images(input_path,work_path):
    unzipped_path=os.path.join(work_path,'unzipped_images')
    makedirs(unzipped_path)

    image_paths=[]
    with zipfile.ZipFile(input_path,'r') as zf:
        infolist=list(zf.infolist())

        for info in infolist:
            if os.path.isabs(info.filename):
                fatal('zip file contains absolute path: %s'%info.filename)

        for info_index,info in enumerate(infolist):
            image_path=os.path.join(unzipped_path,info.filename)
            makedirs(os.path.dirname(image_path))

            if not os.path.isfile(image_path):
                with open(image_path,'wb') as f:
                    f.write(zf.read(info.filename))

            image_paths.append(image_path)

    return image_paths

##########################################################################
##########################################################################

# PaletteRegion=collections.namedtuple('PaletteRegion','palette ybegin yend')
class PaletteRegion:
    def __init__(self,palette,rect):
        self.palette=palette
        self.rect=rect
        self.image_path=None
        self.interesting=None

OverridePaletteRegion=collections.namedtuple('OverridePaletteRegion','palette top bottom')

# TODO: naming...
class Game2:
    def __init__(self,name,gid,image_path):
        self.name=name
        self.gid=gid
        self.was_lossy_image=None
        self.image_path=image_path
        self.quantized_image_path=None
        self.image_size=None
        self.image=None
        self.palette_regions=[]

        # spot override haxx for some of the logic.
        self.override_interesting=False
        self.override_palette=None
        self.override_rect=None
        self.override_regions=None

##########################################################################
##########################################################################

def get_games_dict(image_paths):
    games=[]

    game_id_re=re.compile(r'''(?P<name>.*)-(?P<gid>[0-9]+)''')

    for image_path in image_paths:
        name=os.path.splitext(os.path.basename(image_path))[0]
        m=game_id_re.match(name)
        if m is None: fatal('unexpected image name: %s'%name)

        name=m.group('name')
        
        game=Game2(name,
                   int(m.group('gid')),
                   image_path)

        games.append(game)

    game_by_gid={}
    for game in games:
        if game.gid in game_by_gid:
            fatal('duplicate gid: %s, %s'%(game.name,
                                          game_by_gid[game.id].name))

        game_by_gid[game.gid]=game

    return game_by_gid

##########################################################################
##########################################################################

def run_jobs(name,jobs,executor):
    if len(jobs)==0: return []

    print('%s:'%name)
    
    all_good=True
    num_completed=0
    futures=[executor.submit(*job) for job in jobs]

    results=[]

    for future in concurrent.futures.as_completed(futures):
        num_completed+=1

        prefix='%d/%d'%(num_completed,len(futures))

        try:
            results.append(future.result())
            sys.stdout.write('  %s\r'%prefix)
        except Exception as e:
            print('  %s: failed: %s'%(prefix,e))
            traceback.print_exc()
            all_good=False
        sys.stdout.flush()

    print()

    if not all_good: fatal('%s failed'%name)

    return results

def run_thread_pool_jobs(name,jobs):
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor: return run_jobs(name+' (thread pool)',jobs,executor)

def run_process_pool_jobs(name,jobs):
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor: return run_jobs(name+' (process pool)',jobs,executor)

##########################################################################
##########################################################################

def convert_to_pngs(game_by_gid):
    def convert_to_png(src_path,dest_path):
        result=subprocess.run(['convert',src_path,dest_path],check=True)
    
    jobs=[]
    for game in list(game_by_gid.values()):
        base,ext=os.path.splitext(game.image_path)

        ext=ext.lower()

        if ext=='.png': game.was_lossy_image=False
        elif ext=='.gif':
            # there's exactly 1 .gif, and "convert SRC DEST"
            # doesn't handle it, possibly because it looks like
            # it's an animated one.
            #
            # luckily, the game is mode 7 , so the screen grab is
            # irrelevant. Get rid of it.
            del game_by_gid[game.gid]
        else:
            game.was_lossy_image=True
            png_path=base+'.png'
            if not os.path.isfile(png_path):
                jobs.append((convert_to_png,game.image_path,png_path))
            game.image_path=png_path

    run_thread_pool_jobs('convert images to .png',jobs)

##########################################################################
##########################################################################

def mkdir_and_open(path,mode):
    makedirs(os.path.dirname(path))

    return open(path,mode)
    

def save_indexed_png(path,image,palette):
    assert isinstance(path,str),type(path)
    assert isinstance(image,list),type(image)

    with mkdir_and_open(path,'wb') as f:
        png.Writer(width=len(image[0]),
                   height=len(image),
                   greyscale=False,
                   palette=palette).write(f,image)

def save_linear_rgb_png(path,image):
    srgb_image=[]
    for row in image:
        srgb_row=bytearray()
        assert len(row)==len(image[0])
        for i,x in enumerate(row):
            assert x>=0 and x<=1
            x2=int(math.pow(x,1/GAMMA)*255)
            assert x2>=0 and x2<=255
            srgb_row.append(x2)
        srgb_image.append(srgb_row)
    with mkdir_and_open(path,'wb') as f:
        png.Writer(width=len(image[0])//3,
                   height=len(image),
                   greyscale=False,
                   alpha=False).write(f,srgb_image)

def get_image_bbox(image):
    border_row=bytes(len(image[0]))
    rect_top=0
    while rect_top<len(image):
        if image[rect_top]!=border_row: break
        rect_top+=1

    if rect_top==len(image):
        # entire image is black. uhh, ok.
        return Rect(left=0,top=0,right=len(image[0]),bottom=len(image))
    else:
        rect_bottom=len(image)
        while rect_bottom>rect_top:
            if image[rect_bottom-1]!=border_row: break
            rect_bottom-=1

        def is_border_column(x):
            for y in range(rect_top,rect_bottom):
                if image[y][x]!=0: return False
            return True

        rect_left=0
        while rect_left<len(image[0]):
            if not is_border_column(rect_left): break
            rect_left+=1

        rect_right=len(image[0])
        while rect_right>rect_left:
            if not is_border_column(rect_right-1): break
            rect_right-=1

        return Rect(left=rect_left,
                    top=rect_top,
                    right=rect_right,
                    bottom=rect_bottom)

        
##########################################################################
##########################################################################

GAMMA=2.2

def get_l_from_g(x):
    assert x>=0 and x<=1
    return math.pow(x,GAMMA)

def get_g_from_l(x):
    assert x>=0 and x<=1
    return math.pow(x,1/GAMMA)


def blend_srgb_element(a,b):
    fa=a/255
    assert fa>=0 and fa<=1

    fb=b/255
    assert fb>=0 and fb<=1
    
    alin=math.pow(fa,GAMMA)
    blin=math.pow(fb,GAMMA)

    return (alin+blin)*.5

# def blend_rgba(rgba0,rgba1):
#     return (blend_element(rgba0[0],rgba1[0]),
#             blend_element(rgba0[1],rgba1[1]),
#             blend_element(rgba0[2],rgba1[2]),
#             255)

##########################################################################
##########################################################################

HSV=collections.namedtuple('HSV','h s v bad')

def get_hsv(r,g,b):
    assert r>=0 and r<=1
    assert g>=0 and g<=1
    assert b>=0 and b<=1
    
    M=max(r,g,b)
    m=min(r,g,b)
    C=M-m

    bad=False
    if C==0:
        h_=0               # choice is arbitrary
        bad=True
    elif M==r:
        h_=((g-b)/C)%6
        assert ((h_>=5 and h_<6) or (h_>=0 and h_<=1)),(r,g,b,h_)
    elif M==g:
        h_=((b-r)/C)+2
        assert h_>=1 and h_<=3,(r,g,b,h_)
    elif M==b:
        h_=((r-g)/C)+4
        assert h_>=3 and h_<=5,(r,g,b,h_)

    v=0.2627*r+0.6780*g+0.0593*b
    assert v>=0 and v<=1

    if M==0: s=0
    else: s=C/M

    # if v==0: s=0
    # else:
    #     s=C/v
    #         if s<0: s=0.0
    #         elif s>1: s=1.0

    return HSV(h=h_,s=s,v=v,bad=bad)

##########################################################################
##########################################################################

# def get_saturation(r,g,b):
#     assert r>=0 and r<=1
#     assert g>=0 and g<=1
#     assert b>=0 and b<=1

def quantize_png_job(id,src_path,was_lossy_image,dest_path):
    reader=png.Reader(filename=src_path)
    src_image=reader.asRGBA8()
    src_rows=list(src_image[2])

    if len(src_rows)%2!=0: src_rows.append(src_rows[-1])

    palette=[colour.rgba for colour in BBC_COLOURS]

    # create linear image
    linear_image=[]
    top_y=None
    for y,src_row in enumerate(src_rows):
        assert (isinstance(src_row,bytearray) or
                isinstance(src_row,list)),type(src_row)

        linear_row=[]

        for x in range(src_image[0]):
            i=x*4

            r=src_row[i+0]
            g=src_row[i+1]
            b=src_row[i+2]

            assert r>=0 and r<=255
            assert g>=0 and g<=255
            assert b>=0 and b<=255

            if top_y is None:
                if r!=0 or g!=0 or b!=0: top_y=y

            r=math.pow(r/255,GAMMA)
            g=math.pow(g/255,GAMMA)
            b=math.pow(b/255,GAMMA)

            assert r>=0 and r<=1,r
            assert g>=0 and g<=1,g
            assert b>=0 and b<=1,b
            
            linear_row.append(r)
            linear_row.append(g)
            linear_row.append(b)

        linear_image.append(linear_row)

    if top_y is None: top_y=0

    save_linear_rgb_png(os.path.splitext(dest_path)[0]+'.linear.png',
                        linear_image)

    # shrink vertically
    linear_shrunk_image=[]

    # couldn't figure out how to get good results from this.
    keep_hsv=False
    
    if keep_hsv:
        s_shrunk_image=[]
        v_shrunk_image=[]
        h_shrunk_image=[]

    # print('top_y=%d'%top_y)


    for y in range(top_y%2,len(linear_image)-top_y%2,2):
        rowa=linear_image[y+0]
        rowb=linear_image[y+1]

        linear_shrunk_row=[]

        if keep_hsv:
            h_row=[]
            s_row=[]
            v_row=[]
        
        for x in range(src_image[0]):
            i=x*3
            
            r=(rowa[i+0]+rowb[i+0])*.5
            g=(rowa[i+1]+rowb[i+1])*.5
            b=(rowa[i+2]+rowb[i+2])*.5

            assert r>=0 and r<=1
            assert g>=0 and g<=1
            assert b>=0 and b<=1

            linear_shrunk_row.append(r)
            linear_shrunk_row.append(g)
            linear_shrunk_row.append(b)

            if keep_hsv:
                hsv=get_hsv(r,g,b)

                if hsv.bad:
                    if hsv.v<0.5: h_row+=[0,0,0]
                    else: h_row+=[1,1,1]
                else:
                    if hsv[0]<.5: h_row+=[1,0,0]
                    elif hsv[0]<1.5: h_row+=[1,1,0]
                    elif hsv[0]<2.5: h_row+=[0,1,0]
                    elif hsv[0]<3.5: h_row+=[0,1,1]
                    elif hsv[0]<4.5: h_row+=[0,0,1]
                    elif hsv[0]<5.5: h_row+=[1,0,1]
                    else: h_row+=[1,0,0]

                s_row.append(hsv.s)
                s_row.append(hsv.s)
                s_row.append(hsv.s)

                v_row.append(hsv.v)
                v_row.append(hsv.v)
                v_row.append(hsv.v)

        linear_shrunk_image.append(linear_shrunk_row)

        if keep_hsv:
            h_shrunk_image.append(h_row)
            s_shrunk_image.append(s_row)
            v_shrunk_image.append(v_row)

    save_linear_rgb_png(os.path.splitext(dest_path)[0]+'.linear_shrunk.png',
                        linear_shrunk_image)

    if keep_hsv:
        save_linear_rgb_png(os.path.splitext(dest_path)[0]+'.h_shrunk.png',
                            h_shrunk_image)
        save_linear_rgb_png(os.path.splitext(dest_path)[0]+'.s_shrunk.png',
                            s_shrunk_image)
        save_linear_rgb_png(os.path.splitext(dest_path)[0]+'.v_shrunk.png',
                            v_shrunk_image)

    # bbcify
    bbc_image=[]
    for linear_shrunk_row in linear_shrunk_image:
        bbc_row=bytearray(src_image[0])
        
        for x in range(src_image[0]):
            i=x*3

            r=get_g_from_l(linear_shrunk_row[i+0])
            g=get_g_from_l(linear_shrunk_row[i+1])
            b=get_g_from_l(linear_shrunk_row[i+2])

            assert r>=0 and r<=1
            assert g>=0 and g<=1
            assert b>=0 and b<=1

            # hsv=get_hsv(r,g,b)
            # if hsv[0] is None:
            #     if r<0.5: closest_i=0
            #     else: closest_i=7
            # else:
            #     if hsv[1]<0.1: closest_i=0
            #     else:
            #         assert hsv[0]>=0 and hsv[0]<6
            #         if hsv[0]<.5: closest_i=1
            #         elif hsv[0]<1.5: closest_i=3
            #         elif hsv[0]<2.5: closest_i=2
            #         elif hsv[0]<3.5: closest_i=6
            #         elif hsv[0]<4.5: closest_i=4
            #         elif hsv[0]<5.5: closest_i=5
            #         else: closest_i=1
            
            closest_dist_sq=100000.
            closest_i=0
            for i,bbc_colour in enumerate(BBC_COLOURS):
                dr=r-bbc_colour.frgb[0]
                dg=g-bbc_colour.frgb[1]
                db=b-bbc_colour.frgb[2]
                dist_sq=dr*dr+dg*dg+db*db
                if dist_sq<closest_dist_sq:
                    closest_dist_sq=dist_sq
                    closest_i=i

            bbc_row[x]=closest_i

        bbc_image.append(bbc_row)
            
    save_indexed_png(dest_path,bbc_image,palette)

    return None

def quantize_pngs(game_by_gid,work_path):
    print(BBC_COLOURS)
    jobs=[]
    for game in list(game_by_gid.values()):
        assert game.quantized_image_path is None
        game.quantized_image_path=os.path.join(
            os.path.join(work_path,'quantized'),
            game.name[0],
            '%s.%d.quantized.png'%(game.name,
                                   game.gid))

        if not os.path.isfile(game.quantized_image_path):
            jobs.append((quantize_png_job,
                         game.gid,
                         game.image_path,
                         game.was_lossy_image,
                         game.quantized_image_path))

    run_process_pool_jobs('quantize images',jobs)

##########################################################################
##########################################################################

LoadImageResult=collections.namedtuple('LoadImageResult','gid w h image')

def load_image_job(gid,path):
    reader=png.Reader(filename=path)
    image=reader.read()#asRGBA8()

    result=LoadImageResult(gid=gid,w=image[0],h=image[1],image=[])

    for row in image[2]:
        if isinstance(row,bytearray): result.image.append(bytes(row))
        elif isinstance(row,list): result.image.append(bytes(row))
        elif isinstance(row,array.array):
            assert row.typecode=='B',row.typecode
            result.image.append(bytes(row))
        else: assert False,type(row)

    return result

def load_quantized_pngs(game_by_gid,print_image_sizes):
    jobs=[]
    for game in list(game_by_gid.values()):
        assert game.image_size is None
        assert game.image is None

        jobs.append((load_image_job,
                     game.gid,
                     game.quantized_image_path))

    results=run_process_pool_jobs('load images',jobs)
    for result in results:
        game=game_by_gid[result.gid]

        assert game.image is None
        assert game.image_size is None

        game.image_size=(result.w,result.h)
        game.image=result.image

    if print_image_sizes:
        games_by_image_size={}
        for game in game_by_gid.values():
            games_by_image_size.setdefault(game.image_size,[]).append(game)

        for size,games in games_by_image_size.items():
            line='  %s: %s'%(size,len(games))
            if len(games)<=3:
                line+=' (%s)'%('; '.join([game.name for game in games]))
            print(line)
    
##########################################################################
##########################################################################

# As Windows RECT: (left,top) inclusive, (right,bottom) exclusive.
Rect=collections.namedtuple('Rect','left top right bottom')

def rect_ys(rect): return range(rect.top,rect.bottom)
def rect_xs(rect): return range(rect.left,rect.right)
def rect_w(rect): return rect.right-rect.left
def rect_h(rect): return rect.bottom-rect.top
def rect_union(a,b):
    return Rect(left=min(a.left,b.left),
                top=min(a.top,b.top),
                right=max(a.right,b.right),
                bottom=max(a.bottom,b.bottom))

GetImagePaletteResult=collections.namedtuple('GetImagePaletteResult','gid pixel_counts rect palette_regions')

def get_image_palette_job(gid,
                          image,
                          was_lossy,
                          override_rect,
                          override_palette,
                          override_regions):
    if override_rect is not None:
        # the override rect is specified in pre-shrunk coordinates.
        rect=Rect(left=override_rect[0],
                  top=override_rect[1]//2,
                  right=override_rect[2],
                  bottom=override_rect[3]//2)
    else:
        # BBC border is always black. Strip it out.
        rect=get_image_bbox(image)

    row_pixel_counts=[]
    for row in image: row_pixel_counts.append([0]*8)

    for y in rect_ys(rect):
        for x in rect_xs(rect):
            row_pixel_counts[y][image[y][x]]+=1

    # row_pixel_counts=[0]*rect_h(
    # for y in rect_ys(rect):
    #     for x in rect_xs(rect):
    #         pixel_counts[image[y][x]]+=1

    if was_lossy:
        # lossy compression makes a bit of a mess, so make half an
        # attempt to fix it up.
        #
        # assume any pixel that is occurs only a handful of times in
        # the row is an outlier.
        threshold=rect_w(rect)/100
        for y in range(len(image)):
            for c in range(8):
                if row_pixel_counts[y][c]>0:
                    if row_pixel_counts[y][c]<threshold:
                        row_pixel_counts[y][c]=0
                        # ...and log?
        
        # for y in rect_ys(rect):
        #     for x in rect_xs(rect):
        # threshold=(rect_w(rect)*rect_h(rect))//100
        # for i,n in enumerate(pixel_counts):
        #     if n<threshold: pixel_counts[i]=0

    pixel_counts=[0]*8
    for y in range(len(image)):
        for c in range(8):
            pixel_counts[c]+=row_pixel_counts[y][c]

    # find colours used per row.
    row_palette=[None]*len(image)
    for y in rect_ys(rect):
        row_palette[y]=0
        for x in rect_xs(rect):
            c=image[y][x]
            assert c>=0 and c<8
            if row_pixel_counts[y][c]>0: row_palette[y]|=1<<c

    # build up list of regions
    regions=[]
    palette=None
    top=None
    bottom=None

    def add_region():
        assert top is not None
        assert bottom is not None
        assert palette is not None
        regions.append(PaletteRegion(palette,
                                     Rect(left=rect.left,
                                          top=top,
                                          right=rect.right,
                                          bottom=bottom)))

    if override_palette is not None:
        # just one region in this case.
        top=rect.top
        bottom=rect.bottom
        palette=override_palette
    elif override_regions is not None:
        next_top=0
        for region in override_regions:
            top=region.top or next_top
            bottom=region.bottom or rect.bottom
            palette=0
            for i in region.palette: palette|=1<<i
            add_region()
            next_top=bottom
            
    else:
        for y in rect_ys(rect):
            if palette is not None:
                assert top is not None
                assert bottom is not None

                if row_palette[y]==palette: bottom=y+1
                else:
                    add_region()
                    top=None
                    bottom=None
                    palette=None

            if palette is None:
                assert top is None
                assert bottom is None
                top=y
                bottom=y+1
                palette=row_palette[y]

    add_region()

    # merge adjacent regions if the union would be <=4 colours. (this
    # is a crude metric, but only 4 colour palettes are on topic...)
    i=0
    while i<len(regions)-1:
        union=regions[i+0].palette|regions[i+1].palette
        if POPCOUNT[union]<=4:
            regions[i]=PaletteRegion(palette=union,
                                     rect=rect_union(regions[i].rect,
                                                     regions[i+1].rect))
            del regions[i+1]
        else: i+=1

    return GetImagePaletteResult(gid=gid,
                                 pixel_counts=pixel_counts,
                                 rect=rect,
                                 palette_regions=regions)

def get_palettes(game_by_gid,
                 print_palette_regions):
    jobs=[]
    for game in list(game_by_gid.values()):
        jobs.append((get_image_palette_job,
                     game.gid,
                     game.image,
                     game.was_lossy_image,
                     game.override_rect,
                     game.override_palette,
                     game.override_regions))

    results=run_process_pool_jobs('get stats',jobs)

    result_by_gid={}
    for result in results:
        assert result.gid not in result_by_gid
        result_by_gid[result.gid]=result
        
        game=game_by_gid[result.gid]
        game.palette_regions=result.palette_regions

    for gid in sorted(game_by_gid.keys()):
        game=game_by_gid[gid]
        result=result_by_gid[gid]

        colours=[]
        for i in range(8):
            n=result.pixel_counts[i]
            if n>0: colours.append('%s: %d'%(BBC_COLOURS[i].name,n))

        line='%s (%d): [%s] [%s]; [%d regions'%(game.name,
                                                gid,
                                                result.rect,
                                                '; '.join(colours),
                                                len(game.palette_regions))
        if len(game.palette_regions)>0:
            line+=': ['
            any=False
            for r in game.palette_regions:
                if any: line+='; '
                line+='palette=%d (0x%x) (%s)'%(r.palette,
                                                r.palette,
                                                PALETTE_STRINGS[r.palette])
                line+=' y=%d-%d'%(r.rect.top,r.rect.bottom)
                any=True
            line+=']'

        if game.was_lossy_image:
            if len(colours)>4:
                line+=' [lossy: N=%d]'%(len(colours))

        #
        all_2bit=True
        nregions=0
        for region in game.palette_regions:
            if FOUR_COLOUR_PALETTE_INDEX[region.palette] is None:
                if rect_h(region.rect)<=2:
                    # assume this is a slightly inefficient and/or
                    # ill-timed palette switch...
                    pass
                else:
                    all_2bit=False
                    break
            else: nregions+=1
        if all_2bit:
            line+=' [2bpp regions: N=%d]'%(nregions)

        if print_palette_regions: print(line)
        else:
            # yeah, I know, it still did all the work...
            pass

##########################################################################
##########################################################################

SaveGameImagesResult=collections.namedtuple('SaveGameImagesResult','gid paths')

def get_palette_region_image_path(output_path,
                                  gid,
                                  name,
                                  was_lossy_image,
                                  palette_region_index):
    return os.path.join(output_path,
                        'images',
                        'lossy' if was_lossy_image else 'lossless',
                        '%s.%d.%d.png'%(name,gid,palette_region_index))

def save_game_images_job(output_path,
                         gid,
                         name,
                         was_lossy_image,
                         full_image,
                         palette_regions):
    palette=2*[colour.rgb for colour in BBC_COLOURS]
    
    scale=0.2
    for i in range(8): palette[i]=tuple([int(x*scale) for x in palette[i]])

    result=SaveGameImagesResult(gid=gid,
                                paths=[])
    
    for region_index,region in enumerate(palette_regions):
        path=get_palette_region_image_path(output_path,
                                           gid,
                                           name,
                                           was_lossy_image,
                                           region_index)
        image=[]
        for full_row in full_image: image.append(bytearray(full_row))

        for y in rect_ys(region.rect):
            for x in rect_xs(region.rect): image[y][x]+=8

        image2=[]
        for row in image:
            image2.append(row)
            image2.append(row)

        image=image2
        
        # for y,full_row in enumerate(full_image):
        #     row=bytearray(full_image[y])
        #     for x,c in enumerate(full_row):
                
        #     if y>=region.rect.top and y<region.rect.bottom: row=full_row
        #     else:
        #         row=bytearray()
        #         for c in full_row:
        #             assert c>=0 and c<8
        #             row.append(8+c)
        #     image.append(row)

        save_indexed_png(path,image,palette)

        result.paths.append(path)

    return result

def save_images(game_by_gid,path):
    makedirs(path)

    jobs=[]
    for game in game_by_gid.values():
        jobs.append((save_game_images_job,
                     path,
                     game.gid,
                     game.name,
                     game.was_lossy_image,
                     game.image,
                     game.palette_regions))

    n=0
    results=run_process_pool_jobs('save region PNGs',jobs)
    for result in results:
        game=game_by_gid[result.gid]
        for i,path in enumerate(result.paths):
            assert game.palette_regions[i].image_path is None
            game.palette_regions[i].image_path=path
            if path is not None: n+=1

    print(n)

##########################################################################
##########################################################################

def save_interesting_game_images_job(gid,
                                     name,
                                     was_lossy_image,
                                     palette_regions,
                                     work_path,
                                     output_path):
    assert len(palette_regions)>0

    for region_index,region in enumerate(palette_regions):
        if not region.interesting: continue
        
        src_path=get_palette_region_image_path(work_path,
                                               gid,
                                               name,
                                               was_lossy_image,
                                               region_index)
        dest_path=os.path.join(output_path,
                               'images',
                               '%s.%d.%d.png'%(name,
                                               gid,
                                               region_index))
        with open(src_path,'rb') as f: data=f.read()
        with mkdir_and_open(dest_path,'wb') as f: f.write(data)
            
    return None

def save_interesting_images(game_by_gid,
                            work_path,
                            output_path):
    jobs=[]
    for game in game_by_gid.values():
        jobs.append((save_interesting_game_images_job,
                     game.gid,
                     game.name,
                     game.was_lossy_image,
                     game.palette_regions,
                     work_path,
                     output_path))

    run_thread_pool_jobs('save interesting images',jobs)
    
##########################################################################
##########################################################################

def create_script_folder(path,clean,name,telltale_file_name):
    telltale_path=os.path.join(path,telltale_file_name)

    if os.path.isdir(path):
        if not os.path.isfile(telltale_path):
            fatal('%s not obviously owned by this script')

        if clean: shutil.rmtree(path)

    if not os.path.isdir(path):
        os.makedirs(path)
        with open(telltale_path,'wb'): pass

def rgb_stuff(rgb_str):
    try: rgb=int(rgb_str,16)
    except ValueError: fatal('RGB must be a hex value')
    if (rgb&0xffffff)!=rgb: fatal('RGB must be a 24-bit RGB value')

    r=(rgb>>16&0xff)/255
    g=(rgb>>8&0xff)/255
    b=(rgb>>0&0xff)/255

    print('SRGB: (%f,%f,%f)'%(r,g,b))

    r_=math.pow(r,GAMMA)
    g_=math.pow(g,GAMMA)
    b_=math.pow(b,GAMMA)
    
    print('RGB: (%f,%f,%f)'%(r_,g_,b_))
    
    print('SRGB->HSV: %s'%(get_hsv(r,g,b),))
    print('RGB->HSV: %s'%(get_hsv(r_,g_,b_),))

    def get_closest_bbc_colour(r,g,b):
        closest=None
        closest_dist_sq=1000000
        for colour in BBC_COLOURS:
            dr=r-colour.frgb[0]
            dg=g-colour.frgb[1]
            db=b-colour.frgb[2]

            dist_sq=dr*dr+dg*dg+db*db
            if dist_sq<closest_dist_sq:
                closest_dist_sq=dist_sq
                closest=colour

        return closest

    print('SRGB->BBC: %s'%(get_closest_bbc_colour(r,g,b),))
    print('RGB->BBC: %s'%(get_closest_bbc_colour(r_,g_,b_),))

##########################################################################
##########################################################################

def get_filtered_output_games_list(game_by_gid,pred,name):
    games=list(game_by_gid.values())
    if pred is not None: games=[game for game in games if pred(game)]
    print('%s: %d/%d'%(name,len(games),len(game_by_gid)))

    games.sort(key=lambda game:game.name)

    return games

def save_full_table(game_by_gid,pred,name,output_path):
    games=get_filtered_output_games_list(game_by_gid,pred,name)

    with open(os.path.join(output_path,'%s.html'%name),'wt') as f:
        w=HTMLWriter(f)
        with w.el('html'):
            with w.el('head'):
                with w.el('title'):
                    w.write('%s (full)'%name)

            with w.el('body'):
                with w.el('table',{'border':1}):
                    for game in games:
                        with w.el('tr'):
                            with w.el('td'):
                                w.write(game.name)
                                w.vel('p')
                                w.write('id=%d'%game.gid)
                                w.vel('p')
                                w.write('lossy=%s'%game.was_lossy_image)

                            for region_index,region in enumerate(game.palette_regions):
                                with w.el('td'):
                                    w.vel('img',
                                          {'src':region.image_path,
                                           'width':160,
                                           'height':128})
                                    w.vel('br')
                                    w.write('i=%d t=%d b=%d'%
                                            (region_index,
                                             region.rect.top,
                                             region.rect.bottom))

##########################################################################
##########################################################################

def save_palette_table(indexes,
                       palette_uses,
                       name,
                       output_path):
    print('%s: %s'%(name,indexes))
    def write_columns(w,palette_index):
        u=palette_uses[palette_index]
        assert u.index==palette_index

        with w.el('td'):
            w.write('%d total; %d unsplit; %d split'%(u.num_total,
                                                      u.num_unsplit,
                                                      u.num_split))
        
    write_palette_html(os.path.join(output_path,'%s.html'%name),
                       name,
                       indexes,
                       write_columns)

##########################################################################
##########################################################################

RegionImage=collections.namedtuple('RegionImage','game region_index')

def save_palette_and_games_table(indexes,
                                 game_by_gid,
                                 pred,
                                 name,
                                 output_path,debug):
    games=get_filtered_output_games_list(game_by_gid,pred,name)

    region_images_by_palette_index={}
    for game in games:
        for region_index,region in enumerate(game.palette_regions):
            if not region.interesting: continue
            
            index=FOUR_COLOUR_PALETTE_INDEX[region.palette]
            if index is not None:
                palette=FOUR_COLOUR_PALETTES[index]
                region_images_by_palette_index.setdefault(index,[]).append(RegionImage(game=game,region_index=region_index))

    images_per_row=7

    def write_columns(w,palette_index):
        images=region_images_by_palette_index[palette_index]

        with w.el('td'):
            with w.el('table'):
                num_rows=(len(images)+images_per_row-1)//images_per_row
                for y in range(num_rows):
                    with w.el('tr'):
                        for x in range(images_per_row):
                            i=y*images_per_row+x
                            if i>=len(images): break

                            url='https://bbcmicro.co.uk/game.php?id=%d'%images[i].game.gid
                            region=images[i].game.palette_regions[images[i].region_index]
                            img_path=os.path.join('images',
                                                  os.path.basename(region.image_path))
                            
                            with w.el('td'):
                                with w.el('a',{'href':url}):
                                    w.vel('img',{'src':img_path,
                                                 'width':160,
                                                 'height':128})

                                if debug:
                                    w.vel('br')
                                    w.write('i=%d t=%d b=%d p=%d'%
                                            (images[i].region_index,
                                             region.rect.top,
                                             region.rect.bottom,
                                             region.palette))

    write_palette_html(os.path.join(output_path,'%s.html'%name),
                       name,
                       indexes,
                       write_columns)

##########################################################################
##########################################################################

class PaletteUses:
    def __init__(self,index):
        self.index=index
        self.num_split=0
        self.num_unsplit=0

    @property
    def num_total(self): return self.num_split+self.num_unsplit

def save_output_files(game_by_gid,
                      output_path,
                      debug):

    palette_uses_by_index=[]
    for i in range(len(FOUR_COLOUR_PALETTES)):
        palette_uses_by_index.append(PaletteUses(i))

    for game in game_by_gid.values():
        for region in game.palette_regions:
            if not region.interesting: continue
            
            index=FOUR_COLOUR_PALETTE_INDEX[region.palette]
            if index is not None:
                u=palette_uses_by_index[index]
                assert u.index==index
                if len(game.palette_regions)>1: u.num_split+=1
                elif len(game.palette_regions)==1: u.num_unsplit+=1
                else: assert False,(game.name,game.gid)

    # for u in palette_uses_by_index:
    #     print('index=%d: total=%d split=%d unsplit=%d'%(u.index,
    #                                                     u.num_total,
    #                                                     u.num_split,
    #                                                     u.num_unsplit))

    for sort_by_count in [False,True]:
        for split in [None,False,True]:
            if split is None:
                get_count=lambda u: u.num_total
                is_game_relevant=None
            elif split:
                get_count=lambda u: u.num_split
                is_game_relevant=lambda g: len(g.palette_regions)>1
            else:
                get_count=lambda u: u.num_unsplit
                is_game_relevant=lambda g: len(g.palette_regions)==1

            palette_uses=palette_uses_by_index[:]
            palette_uses.sort(key=lambda u: u.index)
            if sort_by_count:
                palette_uses.sort(key=get_count,reverse=True)

            suffix=''
            
            if split is None: suffix+='.all'
            elif split: suffix+='.split'
            else: suffix+='.unsplit'
            
            if sort_by_count: suffix+='.by_count'
            else: suffix+='.by_index'

            used_palette_indexes=[]
            for u in palette_uses:
                if get_count(u)>0:
                    used_palette_indexes.append(u.index)
            
            save_palette_table(used_palette_indexes,
                               palette_uses_by_index,
                               'palette_uses'+suffix,
                               output_path)

            # no point saving 2 copies of this...!
            if not sort_by_count:
                unused_palette_indexes=[]
                for u in palette_uses:
                    if get_count(u)==0:
                        unused_palette_indexes.append(u.index)

                save_palette_table(unused_palette_indexes,
                                   palette_uses_by_index,
                                   'unused_palettes'+suffix,
                                   output_path)

            save_palette_and_games_table(used_palette_indexes,
                                         game_by_gid,
                                         is_game_relevant,
                                         'games'+suffix,
                                         output_path,
                                         debug)

##########################################################################
##########################################################################

def filter_games(game_by_gid,name_patterns):
    if len(name_patterns)==0: return

    name_patterns=[name_pattern.lower() for name_pattern in name_patterns]

    for gid in game_by_gid.keys():
        game=game_by_gid[gid]

        keep=False
        for name_pattern in name_patterns:
            if fnmatch.fnmatch(game.name.lower(),name_pattern):
                keep=True
                break

        if not keep: del game_by_gid[gid]

def main2(options):
    global g_verbose
    g_verbose=options.verbose

    if options.rgb is not None: return rgb_stuff(options.rgb)

    # create work folder.
    telltale_name='7F6E78AF-B15A-4B4E-B64B-3DE0128CF712'
    create_script_folder(options.output_path,
                         options.clean,
                         'output path',
                         telltale_name)

    work_folder_name='work'
    
    with open(os.path.join(options.output_path,
                           '.gitignore'),'wt') as f:
        f.write('/%s/\n'%work_folder_name)

        # leave the telltale file in place, so the output folder can
        # be updated from another system. The work folder will be
        # regenerated as required.

        # f.write('/%s\n'%telltale_name)

    work_path=os.path.join(options.output_path,work_folder_name)
    makedirs(work_path)
    
    output_path=os.path.join(options.output_path,'htdocs')
    makedirs(output_path)

    if options.clean_images: rmtree(os.path.join(output_path,'images'))

    # write palette summary page.
    write_palette_html(os.path.join(output_path,'palettes.html'),
                       'All BBC Micro Mode 1/5 Palettes')

    # unzip all images into work folder, as-is from the zip file.
    print('unzip images')
    image_paths=unzip_images(options.input_path,work_path)

    # get games list
    game_by_gid=get_games_dict(image_paths)

    # explicitly mark interesting multi-region games.
    #
    # this proved a complete pain to try to do automatically.
    # Scrolling through a list and picking them out manually? Took
    # about 15 minutes. 
    #
    # (see also: save_interesting_game_images_job)

    def interesting(name,gid=None,palette=None,rect=None,regions=None):
        num_found=0
        for game in game_by_gid.values():
            if (game.name.lower()==name.lower() and
                (gid is None or game.gid==gid)):
                num_found+=1
                
                game.override_interesting=True

                if palette is not None:
                    assert regions is None
                    assert len(palette)==4,(name,gid,palette)
                    assert len(set(palette))==4,(name,gid,palette)
                    assert game.override_palette is None,(name,gid,game.override_palette)

                    game.override_palette=0
                    for i in range(4):
                        assert palette[i]>=0 and palette[i]<8,(name,gid,i,palette)
                        game.override_palette|=1<<palette[i]

                if regions is not None:
                    assert palette is None

                    for region in regions:
                        assert isinstance(region,OverridePaletteRegion)

                    game.override_regions=regions

                if rect is not None:
                    assert ((isinstance(rect,tuple) and len(rect)==4) or
                            isinstance(rect,Rect)),(name,gid,rect)
                    assert game.override_rect is None,(name,gid,game.override_rect)

                    game.override_rect=Rect(left=rect[0],
                                            top=rect[1],
                                            right=rect[2],
                                            bottom=rect[3])

        if gid is not None: assert num_found==1
        else: assert num_found>=1
    
    interesting('Alphatron')
    # interesting('Atomix') # mode 2
    interesting('Aviatorhack')
    interesting('BarbarianTheUltimateWarrior')
    interesting('BarbarianIIDungeonOfDrax')
    interesting('Beebchase')
    interesting('BeverlyHillsCop')
    interesting('BigKO')
    interesting('Blockbusters')
    interesting('Boffin',palette=(0,5,6,7))      # 0+5+6+7 (got squished?)
    interesting('BuffaloBillsRodeoGames')
    interesting('ByFairMeansOrFoul',gid=741,rect=Rect(0,0,576,384))
    interesting('CircusGames')
    interesting('CommonwealthGames86')
    interesting('CrazeeRider')
    interesting('EType')
    interesting('Elitedisc')
    interesting('EmlynHughesArcadeQuiz')
    interesting('FutureShock')
    interesting('GenesisProject')
    interesting('GeoffCapesStrongMan')
    interesting('Goal')
    interesting('HelterSkelter',gid=894) # 894=good
    interesting('HolyHorrors')
    interesting('Hostages')
    interesting('IndoorSports')
    interesting('JumpJet',gid=261) # id=261
    interesting('JustifiedSadism')
    interesting('KarateCombat')
    interesting('KissinKousins')
    interesting('LastNinja')
    interesting('LastNinja2')
    interesting('LostCrystal')
    interesting('ManicMiner2021')
    interesting('Mikie')
    interesting('MoonbaseBeta')
    # interesting('Mover')
    interesting('Nutcraka')
    # interesting('Newmarket')
    interesting('Nevryon')
    interesting('OlympicDecathlon')
    interesting('OmegaOrb')
    interesting('Phantom')
    interesting('Pipeline',gid=842,palette=(0,1,3,4)) # 842
    interesting('Predator',
                regions=(OverridePaletteRegion(palette=(0,4,5,6),
                                               top=None,
                                               bottom=76),
                         OverridePaletteRegion(palette=(0,1,2,3),
                                               top=None,
                                               bottom=None)))
    # interesting('ProBoxingSimulator') # annoying mucky jpeg...!
    interesting('Psycastria',palette=(0,2,4,7))
    interesting('Psycastria2',palette=(0,1,3,6)) # 0+1+3+6 (jpegs)
    interesting('RaidOverMoscow')     # 
    interesting('ReptonInfinity',palette=(0,2,3,4))     # 0+2+3+4 (jpegs)
    interesting('ReptonInfinityhack',palette=(0,2,3,4)) # 0+2+3+4 (jpegs)
    interesting('Revs')
    interesting('Revs4Tracks')
    # interesting('Scramble')
    interesting('Sentineltape',palette=(0,2,4,7))
    # interesting('Shark') # it's mode 2!
    interesting('SkirridTheShapesGame')
    interesting('SkoolDaze')
    interesting('SphereOfDestiny')
    interesting('SphereOfDestiny2')
    interesting('Spycat')
    interesting('SpyvsSpy')
    interesting('Starquake')
    interesting('StarClash')
    interesting('StuntCarRacer',
                regions=(OverridePaletteRegion(palette=(0,1,3,4),
                                               top=None,
                                               bottom=40),
                         OverridePaletteRegion(palette=(0,1,3,6),
                                               top=None,
                                               bottom=189),
                         OverridePaletteRegion(palette=(0,1,3,4),
                                               top=None,
                                               bottom=None)))
                
    interesting('SummerOlympiad')
    interesting('SuperiorSoccer')
    interesting('SupermanManOfSteel')
    # interesting('Syncronhack') # jpeg
    interesting('WayOfTheExplodingFist',gid=341)
    interesting('WayOfTheExplodingFist',
                gid=2424,
                regions=(OverridePaletteRegion(palette=(0,6,1,7),
                                               top=None,
                                               bottom=70),
                         OverridePaletteRegion(palette=(0,1,7,3),
                                               top=None,
                                               bottom=124),
                         OverridePaletteRegion(palette=(0,4,3,6),
                                               top=None,
                                               bottom=None)))
    interesting('WayOfTheExplodingFist')
    interesting('WinterOlympiad88')
    interesting('WinterOlympics')
    interesting('YieArKungFu')
    interesting('YieArKungFuII')
    interesting('Zen')

    # filter games list.
    filter_games(game_by_gid,options.game_name_patterns)
    if len(game_by_gid)==0: fatal('no games found')

    # ensure every game has a .png.
    convert_to_pngs(game_by_gid)

    # quantize pngs.
    quantize_pngs(game_by_gid,work_path)
    load_quantized_pngs(game_by_gid,options.image_sizes)

    # figure out palette regions.
    get_palettes(game_by_gid,options.palette_regions)

    # save every image for every palette region, even the useless
    # ones.
    save_images(game_by_gid,
                work_path),

    # find the interesting palette regions.
    for game in game_by_gid.values():
        interesting=False
        if len(game.palette_regions)==1: interesting=True
        elif game.override_interesting: interesting=True

        if interesting:
            for region in game.palette_regions:
                # it should only take 2 scanlines to switch the entire
                # palette? But it looks like 4 would be a better
                # threshold for excluding uninteresting images.
                if rect_h(region.rect)>=4:
                    region.interesting=True
        
    save_interesting_images(game_by_gid,work_path,output_path)

    #
    # save_full_table(game_by_gid,None,'all',work_path)
    # save_full_table(game_by_gid,
    #                 lambda g: len(g.palette_regions)>1,
    #                 'split',
    #                 work_path)
    # save_full_table(game_by_gid,
    #                 lambda g: g.was_lossy_image,
    #                 'lossy',
    #                 work_path)
    # save_full_table(game_by_gid,
    #                 lambda g: (g.was_lossy_image and
    #                            len(g.palette_regions)>1),
    #                 'split_lossy',
    #                 work_path)

    #
    save_output_files(game_by_gid,
                      output_path,
                      options.debug)

##########################################################################
##########################################################################

def main(argv):
    parser=argparse.ArgumentParser()

    parser.add_argument('-v','--verbose',action='store_true',help='''be more verbose''')
    parser.add_argument('input_path',metavar='FILE',help='''read bbcmicro.co.uk screenshots from %(metavar)s''')
    parser.add_argument('output_path',metavar='PATH',help='''write stuff to %(metavar)s''')
    parser.add_argument('--clean',action='store_true',help='''delete entire output folder before starting''')
    parser.add_argument('--clean-images',action='store_true',help='''delete output images folder before writing output images''')
    parser.add_argument('--image-sizes',action='store_true',help='''print image sizes''')
    parser.add_argument('--palette-regions',action='store_true',help='''print palette regions''')
    parser.add_argument('-g','--game',action='append',dest='game_name_patterns',default=[],metavar='PATTERN',help='''include only game(s) matching %(metavar)s, a case-insensitive glob pattern''')
    parser.add_argument('--rgb',metavar='RGB',help='''print info about %(metavar)s, hex RGB colour''')
    parser.add_argument('--debug',action='store_true')

    main2(parser.parse_args(argv))

if __name__=='__main__': main(sys.argv[1:])
