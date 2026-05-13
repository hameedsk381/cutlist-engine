; Cutlist Engine G-code
; Sheet 1 | default | 2440.0 x 1220.0 mm | parts=1
; Feed: 2500.0 mm/min  Plunge: 800.0 mm/min  Spindle: 0 RPM
; Cut depth: 6.0 mm  Pass depth: 6.0 mm  Safe Z: 15.0

G17 G21 G90 G94
G54
G0 Z15.000
G4 P1

; --- panel_001  hole  panel_001  default  rotation=90
G0 X1.000 Y129.000
G0 Z2.000
G1 Z-6.000 F800
G1 X1.000 Y71.000 F2500
G1 X99.000 Y71.000 F2500
G1 X99.000 Y129.000 F2500
G1 X1.000 Y129.000
G0 Z15.000

; --- panel_001  outer  panel_001  default  rotation=90
G0 X301.000 Y201.000
G0 Z2.000
G1 Z-6.000 F800
G1 X-1.000 Y201.000 F2500
G1 X-1.000 Y-1.000 F2500
G1 X301.000 Y-1.000 F2500
G1 X301.000 Y201.000
G0 Z15.000

G0 Z15.000
G0 X0 Y0
M30
