from __future__ import annotations

import asyncio
import random
import re
import string
from base64 import b64decode

import aiohttp
import aiofiles # type: ignore
import aiofiles.os # type: ignore
from aiohttp import web

PALETTE_PATTERN = re.compile("^(?:(?:#?[0-9A-F]{6}|X)\,){15}(?:#?[0-9A-F]{6}|X)$")

def gen_id() -> str:
  pool: str = string.ascii_letters + string.digits
  return "".join(random.choices(pool,k=32))

def build_sanjuuni(src: str, out: str, *, 
                   binary: bool = False, 
                   cc_pal: bool = False, 
                   dithering: str = "none", 
                   width: int = None, # type: ignore
                   height: int = None, # type: ignore
                   output: str = "blit",
                    palette: str = None) -> str:
    if dithering not in ["threshold","ordered","lab-color","octree","kmeans","none"]:
      raise ValueError("dithering not in threshold, ordered, lab-color, octree, kmeans, none")
    if output not in ["bimg","nfp"]:
      raise ValueError("output not in bimg, nfp")
    
    builder = "sanjuuni {fmt} {dither} {pal} {h} {w} {b} {palette} --input {src} -o {out}"
    dither = ({
      "threshold": "-t",
      "ordered": "-O",
      "lab-color": "-L",
      "octree": "-8",
      "kmeans": "-k",
      "none": ""
    })[dithering]
    fmt = ({
      "bimg": "-b",
      "nfp": "-n"
    })[output]
    pal = "-p" if cc_pal else ""
    b = "-B" if binary else ""
    w = f"-W {width}" if width else ""
    h = f"-H {height}" if height else ""
    cust_pal = f"--palette {palette.replace('#','')}" if palette else ""
    return builder.format(fmt=fmt,dither=dither,pal=pal,b=b,w=w,h=h, palette=cust_pal, src=src, out=out)

routes = web.RouteTableDef()

@routes.post("/convert")
async def post_convert(request: web.Request) -> web.Response:
  body = await request.json()
  if "url" in body and "data" in body:
    return web.Response(status=400,body="url and data passed in json")
  dithering = body.get("dithering","none")
  use_cc_palette = body.get("cc-palette",False)
  binary = body.get("binary",False)
  width = body.get("width",None)
  if not isinstance(width,int) and width is not None:
    return web.Response(status=400,body="width is not an integer")
  height = body.get("height",None)
  if not isinstance(height,int) and height is not None:
    return web.Response(status=400,body="height is not an integer")
  fmt = body.get("format","blit")

  palette = body.get("palette",None)
  if palette is not None:
    # begin check to ensure it is correct
    if not PALETTE_PATTERN.match(palette):
      return web.Response(status=400,body="palette is invalid!")
  
  if palette is not None and use_cc_palette:
    return web.Response(status=400,body="cc-palette and palette passed")
  
  job_id = gen_id()
  src = f"/tmp/sanjuuni_in{job_id}"
  out: str = f"/tmp/sanjuuni_out{job_id}.{fmt}"

  try:
    cmd = build_sanjuuni(src,out,output=fmt,dithering=dithering,cc_pal=use_cc_palette,binary=binary,width=width,height=height,palette=palette)
    print(cmd)
  except ValueError as e:
    return web.Response(status=400,body=str(e))
  
  data: bytes

  try:
    if "url" in body:
      async with aiohttp.ClientSession() as sess:
        async with sess.get(body["url"]) as resp:
          data = await resp.read()
    elif "data" in body:
      data = b64decode(body["data"])
  except:
    return web.Response(status=400,body="failed parsing data/url")
  
  async with aiofiles.open(src,"wb") as f:
    await f.write(data) #type: ignore
  
  # run sanjuuni with asyncio subprocess
  process = await asyncio.subprocess.create_subprocess_shell(cmd)
  code = await process.wait()
  if code == 0:
    async with aiofiles.open(out) as f:
      lua = await f.read()
    await aiofiles.os.remove(src)
    await aiofiles.os.remove(out)
    return web.Response(body=lua,content_type="text/x-lua")
  else:
    return web.Response(body=f"sanjuuni exited with code {code}",status=500)
  
app = web.Application()
app.add_routes(routes)

web.run_app(app,host="127.0.0.1",port=21500) # type: ignore
