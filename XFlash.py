#!/usr/bin/env python
import usb
import sys
import struct
import pprint
import argparse
import code

pp = pprint.PrettyPrinter()

class ConsoleUI:
  def opStart(self, name):
    sys.stdout.write(name.ljust(40))
    
  def opProgress(self,progress, total=-1):
    if (total >= 0): 
      prstr = "0x%04x / 0x%04x" % (progress, total)
    else:
      prstr = "0x%04x" % (progress)
      
    sys.stdout.write(prstr.ljust(20))
    sys.stdout.write('\x08' * 20)
    sys.stdout.flush()
    
  def opEnd(self, result):
    sys.stdout.write(result.ljust(20))
    sys.stdout.write("\n")

class XFlash:
  def __init__(self, usbdev):
    self.devhandle = usbdev.open()
    self.devhandle.setConfiguration(1)
    self.devhandle.claimInterface(0)
    
    self.ep_out = 0x05
    self.ep_in  = 0x82

  def __del__(self):
    try:
      self.devhandle.releaseInterface(0)
      del self.devhandle
    except:
      pass
            
  def cmd(self, cmd, argA=0, argB=0):
    buffer = struct.pack("<LL", argA, argB)
    self.devhandle.controlMsg(requestType = usb.TYPE_VENDOR,
                              request     = cmd,
                              value       = 0x00,
                              index       = 0x00,
                              buffer      = buffer)

  def flashPowerOn(self):
    self.cmd(0x10)

  def flashShutdown(self):
    self.cmd(0x11)
    
  def update(self):
    self.cmd(0xF0)
      
  def flashInit(self):
    self.cmd(0x03)

    buffer = self.devhandle.bulkRead(self.ep_in, 4, 1000)
    buffer = ''.join([chr(x) for x in buffer])

    return struct.unpack("<L", buffer)[0]

  def flashDeInit(self):
    self.cmd(0x04)    

  def flashStatus(self):
    self.cmd(0x05)

    buffer = self.devhandle.bulkRead(self.ep_in, 4, 1000)
    buffer = ''.join([chr(x) for x in buffer])
    
    return struct.unpack("<L", buffer)[0]
    
  def flashErase(self, block):
    self.cmd(0x06, block)
    return self.flashStatus()
    
  def flashReadBlock(self, block):
    self.cmd(0x01, block, 528 * 32)
    
    buffer = self.devhandle.bulkRead(self.ep_in, 528 * 32, 100000)
    buffer = ''.join([chr(x) for x in buffer])

    status = self.flashStatus()
    
    return (status, buffer)
    
  def flashWriteBlock(self, block, buffer):
    self.cmd(0x02, block, len(buffer))
    
    self.devhandle.bulkWrite(self.ep_out, buffer, 1000)

    return self.flashStatus()    
    
# def calcecc(data):
#   assert len(data) == 0x210
#   val = 0
#   for i in range(0x1066):
#     if not i & 31:
#       v = ~struct.unpack("<L", data[i/8:i/8+4])[0]
#     val ^= v & 1
#     v >>= 1
#     if val & 1:
#       val ^= 0x6954559
#     val >>= 1
# 
#   val = ~val
#   return data[:-4] + struct.pack("<L", (val << 6) & 0xFFFFFFFF)
# 
# def addecc(data, block = 0, off_8 = "\x00" * 4):
#   res = ""
#   while len(data):
#     d = (data[:0x200] + "\x00" * 0x200)[:0x200]
#     data = data[0x200:]
# 
#     d += struct.pack("<L4B4s4s", block / 32, 0, 0xFF, 0, 0, off_8, "\0\0\0\0")
#     d = calcecc(d)
#     block += 1
#     res += d
#   return res


def main(argv):
  parser = argparse.ArgumentParser(description='XBox 360 NAND Flasher')
  subparsers = parser.add_subparsers(title='Operations', dest='action')
  
  parser_read = subparsers.add_parser('read', help='Dumps an image from the NAND')
  parser_read.add_argument('file', nargs=1, type=argparse.FileType('w'), help='The file to dump the NAND to')
  parser_read.add_argument('start', nargs='?', metavar='start', action='store', type=int, default=0, help='The block to start the action from')
  parser_read.add_argument('end', nargs='?', metavar='end', action='store', type=int, default=0x400, help='The count of blocks to perform the action to')
  
  parser_write = subparsers.add_parser('write', help='Writes an image into the NAND')
  parser_write.add_argument('file', nargs=1, type=argparse.FileType('r'), help='The image file to write to the NAND')
  parser_write.add_argument('start', nargs='?', metavar='start', action='store', type=int, default=0, help='The block to start the action from')
  parser_write.add_argument('end', nargs='?', metavar='end', action='store', type=int, default=0x400, help='The count of blocks to perform the action to')
  
  parser_erase = subparsers.add_parser('erase', help='Erases blocks in the NAND')
  parser_erase.add_argument('start', nargs='?', metavar='start', action='store', type=int, default=0, help='The block to start the action from')
  parser_erase.add_argument('end', nargs='?', metavar='end', action='store', type=int, default=0x400, help='The count of blocks to perform the action to')
  
  parser_update = subparsers.add_parser('update', help='Jumps into the bootloader of the NAND Flashing device for updating the firmware')
  parser_shutdown = subparsers.add_parser('shutdown', help='Shuts down the attached XBox 360')
  parser_poweron = subparsers.add_parser('powerup', help='Powers up the attached XBox 360')
  
  arguments = parser.parse_args(argv[1:])

  ui = ConsoleUI()
  usbdev = None
  
  for bus in usb.busses():
    for dev in bus.devices:
      if dev.idVendor == 0xFFFF and dev.idProduct == 4:
        usbdev = dev
  
  if not usbdev:
    print "XFlash USB hardware not found."
    sys.exit(1)
  
  print "Using XFlash @ [%s]" % (usbdev.filename)
  
  xf = XFlash(usbdev)
  
  if arguments.action in ('erase', 'write', 'read'):
    try:
      print "FlashConfig: 0x%08x" % (xf.flashInit())
    except:
      xf.flashDeInit()
  
  if arguments.action == 'erase':
    #start = 0
    #end = (options.flashsize * 1024) / 16
    start = arguments.start
    end = arguments.end
  
    ui.opStart('Erase')
  
    for b in range(start, end):
      ui.opProgress(b, end-1)
      status = xf.flashErase(b)
  
    ui.opEnd('0x%04x blocks OK' % (end))
  
  if arguments.action == 'read':
    #start = 0
    #end = (options.flashsize * 1024) / 16
    start = arguments.start
    end = arguments.end
  
    ui.opStart('Read')
  
    for b in range(start, end):
      ui.opProgress(b, end-1)
      (status, buffer) = xf.flashReadBlock(b)
      arguments.file[0].write(buffer)
  
  if arguments.action == 'write':
    #start = 0
    #end = (options.flashsize * 1024) / 16 
    
    start = arguments.start
    end = arguments.end
    blocksize = 528 * 32
  
    ui.opStart('Write')
  
    for b in range(start, end):
      ui.opProgress(b, end-1)  
      buffer = arguments.file[0].read(blocksize)
      
      if len(buffer) < blocksize:
        buffer += ('\xFF' * (blocksize-len(buffer)))
  
      status = xf.flashWriteBlock(b, buffer)
  
  if arguments.action == 'update':
    xf.update()
  
  if arguments.action == 'powerup':
    xf.flashPowerOn()
  
  if arguments.action == 'shutdown':
    xf.flashShutdown()


if __name__ == '__main__':
  main(sys.argv)
  