#!/usr/bin/python3
#(MacPorts python 3.14 is usefully quicker on my Mac...)
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

# FOUR_COLOUR_PALETTE[INDEX] - INDEX is the index of a 2 bpp palette.
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

Game=collections.namedtuple('Game','png_path id')
GetGamePaletteResult=collections.namedtuple('GetGamePaletteResult','id palette')

##########################################################################
##########################################################################

def get_game_palette(game):
    reader=png.Reader(filename=game.png_path)
    result=reader.asRGBA8()

    palette=0

    for row in result[2]:
        assert len(row)==result[0]*4

        if isinstance(row,bytearray):
            for x in range(0,len(row),4):
                # palette|=1<<((row[x+0]>>7)|
                #              (row[x+1]>>6&2)|
                #              (row[x+2]>>5&4))

                pixel=0

                if row[x+0]>=128: pixel|=1
                if row[x+1]>=128: pixel|=2
                if row[x+2]>=128: pixel|=4

                palette|=1<<pixel
        elif isinstance(row,list):
            for x in range(0,len(row),4):
                r,g,b=row[x+0:x+3]
                assert r>=0 and r<256
                assert g>=0 and g<256
                assert b>=0 and b<256

                pixel=((0 if r<128 else 1)|
                       (0 if g<128 else 2)|
                       (0 if b<128 else 4))

                palette|=1<<pixel

        else: assert False,type(row)

    return GetGamePaletteResult(id=game.id,
                                palette=palette)

##########################################################################
##########################################################################

def write_palette_html(path,
                       title,
                       palette_indexes=None,
                       more_columns_fun=None):
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
                        more_columns_fun(w,palette)

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

class Game:
    def __init__(self,image_path,id_):
        self.png_path=png_path
        self.id=id_
        self.palette=None

def find_games(options):
    game_id_re=re.compile(r'''.*-(?P<id>[0-9]+)\.[^.]+''')
    
    images_folder_path=os.path.join(options.output_path,'unzipped_images')
    makedirs(images_folder_path)

    game_by_id={}
    with zipfile.ZipFile(options.input_path,'r') as zf:
        infolist=list(zf.infolist())

        for info in infolist:
            if os.path.isabs(info.filename):
                fatal('zip file contains absolute path: %s'%info.filename)
                
        for info_index,info in enumerate(infolist):
            print(f'''#{info_index} ({len(infolist)}): {info.filename}''')
            # data=zf.read(info.filename)

            image_path=os.path.join(images_folder_path,info.filename)
            makedirs(os.path.dirname(image_path))

            ext=os.path.splitext(info.filename)[1].lower()

            match=game_id_re.match(info.filename)
            if match is None:
                fatal('unexpected image name: %s'%name)

            game_id=int(match.group('id'))

            if ext=='.png':
                if not os.path.isfile(image_path):
                    with open(image_path,'wb') as f:
                        f.write(zf.read(info.filename))

                png_path=image_path
            elif ext=='.gif':
                # there's exactly 1 .gif, and "convert SRC DEST"
                # doesn't handle it, possibly because it looks like
                # it's an animated one.
                #
                # luckily, the game is mode 7 , so the screen grab is
                # irrelevant.
                continue
            else:
                png_path=image_path+'.png'
                if not os.path.isfile(png_path):
                    with tempfile.NamedTemporaryFile(mode='wb',
                                                     delete=False,
                                                     suffix=ext) as img_f:
                        img_f.write(zf.read(info.filename))
                        img_f.close()

                        result=subprocess.run(['convert',
                                               img_f.name,
                                               png_path],
                                              check=True)
                        
                    os.unlink(img_f.name)

            assert game_id not in game_by_id
            game_by_id[game_id]=Game(png_path,game_id)

    return game_by_id

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
    def __init__(self,palette,top,bottom):
        self.palette=palette
        self.top=top
        self.bottom=bottom
        self.image_path=None

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

##########################################################################
##########################################################################

def get_games_dict(image_paths,name_patterns):
    name_patterns=[name_pattern.lower() for name_pattern in name_patterns]
    
    games=[]

    game_id_re=re.compile(r'''(?P<name>.*)-(?P<gid>[0-9]+)''')

    for image_path in image_paths:
        name=os.path.splitext(os.path.basename(image_path))[0]
        m=game_id_re.match(name)
        if m is None: fatal('unexpected image name: %s'%name)

        name=m.group('name')
        
        if len(name_patterns)==0: append=True
        else:
            append=False
            for name_pattern in name_patterns:
                if fnmatch.fnmatch(name.lower(),name_pattern):
                    append=True
                    break

        
        if append:
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

GetImagePaletteResult=collections.namedtuple('GetImagePaletteResult','gid actual_pixel_counts pixel_counts rect palette_regions')

def get_image_palette_job(gid,image,was_lossy):
    # BBC border is always black. Strip it out.
    rect=get_image_bbox(image)

    pixel_counts=[0]*8
    for y in rect_ys(rect):
        for x in rect_xs(rect):
            pixel_counts[image[y][x]]+=1

    actual_pixel_counts=pixel_counts[:]

    # lossy compression makes a bit of a mess, so make half an attempt
    # to fix it up.
    if was_lossy:
        threshold=(rect_w(rect)*rect_h(rect))//100
        for i,n in enumerate(pixel_counts):
            if n<threshold: pixel_counts[i]=0

    # find colours used per row.
    row_palette=[None]*len(image)
    for y in rect_ys(rect):
        row_palette[y]=0
        for x in rect_xs(rect):
            if pixel_counts[image[y][x]]>0:
                row_palette[y]|=1<<image[y][x]

    # build up list of regions
    regions=[]
    palette=None
    top=None
    bottom=None

    def add_region():
        assert top is not None
        assert bottom is not None
        assert palette is not None
        regions.append(PaletteRegion(top=top,
                                     bottom=bottom,
                                     palette=palette))
    
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
                                     top=regions[i].top,
                                     bottom=regions[i+1].bottom)
            del regions[i+1]
        else: i+=1

    return GetImagePaletteResult(gid=gid,
                                 actual_pixel_counts=actual_pixel_counts,
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
                     game.was_lossy_image))

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
                line+=' y=%d-%d'%(r.top,r.bottom)
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
                if region.bottom-region.top<=2:
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
    palette=[colour.rgba for colour in BBC_COLOURS]
    scale=0.25
    for i in range(8):
        palette.append((int(palette[i][0]*scale),
                        int(palette[i][1]*scale),
                        int(palette[i][2]*scale),
                        255))

    result=SaveGameImagesResult(gid=gid,
                                paths=[])
    
    for region_index,region in enumerate(palette_regions):
        path=get_palette_region_image_path(output_path,
                                           gid,
                                           name,
                                           was_lossy_image,
                                           region_index)
        image=[]
        for y,full_row in enumerate(full_image):
            if y>=region.top and y<region.bottom: row=full_row
            else:
                row=bytearray()
                for c in full_row:
                    assert c>=0 and c<8
                    row.append(8+c)
            image.append(row)

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

    # is this game interesting at all?
    #
    # if there's any 4+-colour region longer than 2 scanlines, assume
    # it's actually an 8-colour game and therefore not.
    interesting=True
    for region in palette_regions:
        if FOUR_COLOUR_PALETTE_INDEX[region.palette] is None:
            if region.bottom-region.top>2:
                interesting=False
                break

    if interesting:
        for region_index,region in enumerate(palette_regions):
            if region.bottom-region.top>=32:
                src_path=get_palette_region_image_path(work_path,
                                                       gid,
                                                       name,
                                                       was_lossy_image,
                                                       region_index)
                split='split' if len(palette_regions)>1 else 'not_split'
                dest_path=os.path.join(output_path,
                                       'images',
                                       split,
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
    
def save_full_table(game_by_gid,pred,name,output_path):
    games=list(game_by_gid.values())

    if pred is not None: games=[game for game in games if pred(game)]

    print('%s: %d/%d'%(name,len(games),len(game_by_gid)))
    
    games.sort(key=lambda game:game.name)

    with open(os.path.join(output_path,'%s.html'%name),'wt') as f:
        w=HTMLWriter(f)
        with w.el('html'):
            with w.el('head'):
                with w.el('title'):
                    w.write(name)

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
                            for region in game.palette_regions:
                                with w.el('td'):
                                    w.vel('img',
                                          {'src':region.image_path,
                                           'width':160,
                                           'height':128})
    
##########################################################################
##########################################################################

interesting_games=[
    'Alphatron',
    'Atomix',
    'Aviatorhack',
    'BarbarianTheUltimateWarrior',
    'BarbarianIIDungeonOfDrax',
    'Beebchase',
    'BeverlyHillsCop',
    'BigKO',
    'Blockbusters',
    'Boffin',                   # 0+5+6+7 (got squished?)
    'BuffaloBillsRodeoGames',
    'ByFairMeansOrFoul',        # needs rect hack
    'CircusGames',
    'CommonwealthGames86',
    'CrazeeRider',
    'EType',
    'Elitedisc',
    'EmlynHughesArcadeQuiz',
    'FutureShock',
    'GenesisProject',
    'GeoffCapesStrongMan',
    'Goal',
    'HelterSkelter',            # 894=good
    'HolyHorrors',
    'Hostages',
    'IndoorSports',
    'JumpJet',                  # id=261
    'JustifiedSadism',
    'KarateCombat',
    'KissinKousins',
    'LastNinja',
    'LastNinja2',
    'LostCrystal',
    'ManicMiner2021',
    'Mikie',
    'MoonbaseBeta',
    'Mover',
    'Nutcraka',
    'Newmarket',
    'Nevryon',
    'OlympicDecathlon',
    'OmegaOrb',
    'Phantom',
    'Pipeline',                 # 842
    'Predator',
    'ProBoxingSimulator',
    'Psycastria2',              # 0+1+3+6 (all mucky jpegs)
    'RaidOverMoscow',
    'ReptonInfinity',           # 0+2+3+4 (jpegs)
    'ReptonInfinityhack',       # 0+2+3+4 (jpegs)
    'Revs',
    'Revs4Tracks',
    'Scramble',
    'Sentineltape',
    'Shark',
    'SkirridTheShapesGame',
    'SkoolDaze',
    'SphereOfDestiny',
    'SphereOfDestiny2',
    'Spycat',
    'SpyvsSpy',
    'Starquake',
    'StarClash',
    'StuntCarRacer',
    'SummerOlympiad',
    'SuperiorSoccer',
    'SupermanManOfSteel',
    'Syncronhack',
    'WayOfTheExplodingFist',
    'WayOfTheExplodingFist',
    'WinterOlympiad88',
    'WinterOlympics',
    'YieArKungFu',
    'YieArKungFuII',
    'Zen',
]

def main2(options):
    global g_verbose
    g_verbose=options.verbose

    if options.rgb is not None: return rgb_stuff(options.rgb)

    # create work folder.
    create_script_folder(options.output_path,
                         options.clean,
                         'output path',
                         '7F6E78AF-B15A-4B4E-B64B-3DE0128CF712')

    work_path=os.path.join(options.output_path,'work')
    makedirs(work_path)
    
    output_path=os.path.join(options.output_path,'output')
    makedirs(output_path)

    if options.clean_images: rmtree(os.path.join(output_path,'images'))

    # write palette summary page.
    write_palette_html(os.path.join(output_path,'palettes.html'),
                       'All BBC Micro Mode 1/5 Palettes')

    # unzip all images into work folder, as-is from the zip file.
    image_paths=unzip_images(options.input_path,work_path)

    # get games list
    game_by_gid=get_games_dict(image_paths,options.
                               game_name_patterns)
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

    # find the interesting palette regions. "interesting" is not
    # precisely defined, but: if there's more than 32 scanlines (8
    # character rows), that's probably good enough.
    save_interesting_images(game_by_gid,work_path,output_path)

    #
    save_full_table(game_by_gid,None,'all',work_path)
    save_full_table(game_by_gid,
                    lambda g: len(g.palette_regions)>1,
                    'split',
                    work_path)
    save_full_table(game_by_gid,
                    lambda g: g.was_lossy_image,
                    'lossy',
                    work_path)
    save_full_table(game_by_gid,
                    lambda g: (g.was_lossy_image and
                               len(g.palette_regions)>1),
                    'split_lossy',
                    work_path)

    # games_by_image_size={}
    # for game in game_by_gid.values():
    #     games_by_image_size.setdefault(game.image_size,[]).append(game)

    # for image_size,games in games_by_image_size.items():
    #     print('%s: %d'%(image_size,len(gam

    return

    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        all_good=True
        futures=[executor.submit(get_game_palette,game) for game in game_by_id.values()]

        num_completed=0
        for future in concurrent.futures.as_completed(futures):
            num_completed+=1

            prefix='%d/%d'%(num_completed,len(futures))
            try:
                result=future.result()
                print('%s: succeeded'%prefix)
            except Exception as e:
                all_good=False
                result=None
                print('%s: failed: %s'%(prefix,e))

            if result is not None:
                assert result.id in game_by_id
                assert game_by_id[result.id].palette is None
                game_by_id[result.id].palette=result.palette

    if not all_good: fatal('failed')

    games_by_palette={}
    for game in game_by_id.values():
        index=FOUR_COLOUR_PALETTE_INDEX[game.palette]
        if index is not None:
            palette=FOUR_COLOUR_PALETTES[index]
            games_by_palette.setdefault(palette,[]).append(game)

    images_folder_name='images'
    makedirs(os.path.join(options.output_path,images_folder_name))

    def add_example_images(w,palette):
        assert w is not None
        assert palette is not None

        games=games_by_palette.get(palette)

        if games is not None:
            games_per_row=8
            with w.el('td'):
                with w.el('table'):
                    for y in range((len(games)+games_per_row-1)//games_per_row):
                        with w.el('tr'):
                            for x in range(games_per_row):
                                i=y*games_per_row+x
                                if i>=len(games): break

                                # don't link to unzipped_images. copy
                                # the thing to another path so it's
                                # all self-contained.
                                img_path='%s/%s'%(images_folder_name,
                                                  os.path.basename(games[i].png_path))
                                shutil.copyfile(
                                    games[i].png_path,
                                    os.path.join(options.output_path,
                                                 img_path))

                                with w.el('td'):
                                    url='https://bbcmicro.co.uk/game.php?id=%d'%games[i].id
                                    with w.el('a',{'href':url}):
                                        w.vel('img',{'src':img_path,
                                                     'width':160,
                                                     'height':128})
        
        # if games is not None:
        #     for i in range(len(games)):
        #         path=os.path.relpath(games[i].png_path,
        #                              options.output_path)
        #         with w.el('td'):
        #             url='https://bbcmicro.co.uk/game.php?id=%d'%games[i].id
        #             with w.el('a',{'href':url}):
        #                 w.vel('img',{'src':path,
        #                              'width':160,
        #                              'height':128})

    palette_indexes=[i for i in range(len(FOUR_COLOUR_PALETTES)) if FOUR_COLOUR_PALETTES[i] in games_by_palette]
                        
    write_palette_html(os.path.join(options.output_path,'images.html'),
                       'Used BBC Micro Mode 1/5 Palettes',
                       palette_indexes,
                       more_columns_fun=add_example_images)

    palette_indexes.sort(key=lambda x: len(games_by_palette[FOUR_COLOUR_PALETTES[x]]))

    write_palette_html(os.path.join(options.output_path,'images_sorted.html'),
                       'Used BBC Micro Mode 1/5 Palettes',
                       palette_indexes,
                       more_columns_fun=add_example_images)

    write_palette_html(os.path.join(options.output_path,
                                    'unused_palettes.html'),
                       'Unused BBC Micro Mode 1/5 Palettes',
                       palette_indexes=[i for i in range(len(FOUR_COLOUR_PALETTES)) if FOUR_COLOUR_PALETTES[i] not in games_by_palette])

    # palettes_seen=set()
    # for result in results:
    #     if FOUR_COLOUR_PALETTE[result.palette] is not None:
    #         palettes_seen.add(result.palette)

    # print(len(palettes_seen))

    
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

    main2(parser.parse_args(argv))

if __name__=='__main__': main(sys.argv[1:])
