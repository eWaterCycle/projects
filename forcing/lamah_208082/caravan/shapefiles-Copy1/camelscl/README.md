To speed up the processing on Google Earth Engine, the original basin polygons from the CAMELS-CL dataset have been simplified using QGIS 3.22.4.
The settings for "Vector" -> "Geometry Tools" -> "Simplify" where:
- Method: Distance (Duglas-Peucker)
- Tolerance: 0.001 degree