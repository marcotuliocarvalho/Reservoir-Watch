from src.ingestion import pipeline

if __name__ == "__main__":
    data = pipeline.run_ingestion()
    data.tail(10).drop_nans(subset=['val_nivelmontante']).collect().write_parquet("arquivo.parquet")