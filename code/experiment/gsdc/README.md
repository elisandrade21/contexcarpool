# Fare rule on real smartphone GNSS (Google Smartphone Decimeter Challenge 2022)

The raw data are not redistributed (Kaggle competition rules). To reproduce:
1. Accept the rules of https://www.kaggle.com/competitions/smartphone-decimeter-2022 and configure the Kaggle CLI.
2. `python3 download.py` (expects `files.csv` from `kaggle competitions files -c smartphone-decimeter-2022 -v`; downloads `ground_truth.csv` and `device_gnss.csv` of the 58 training drives with two or more phones, about 6 GB).
3. `python3 analisar.py` writes `resultado_gsdc.json`.

`PROTOCOLO_2026-11-17.md` (Portuguese) fixes the analysis rules; it was written before the data were opened. Cite: Fu, Khider, van Diggelen, "Android Raw GNSS Measurement Datasets for Precise Positioning", ION GNSS+ 2020, doi:10.33012/2020.17628.
