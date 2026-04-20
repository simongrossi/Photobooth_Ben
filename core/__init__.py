"""core — logique métier du photobooth (pas de pygame display).

Contient :
- logger : logging rotatif + helpers nommés (log_info/warning/critical)
- camera : CameraManager (gphoto2 + threading.Lock + retry)
- montage : MontageGenerator (génération PIL des montages)
- printer : PrinterManager (files CUPS via lpstat/lp)
"""
