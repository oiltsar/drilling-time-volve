.PHONY: all db notebook marts

all: db notebook marts

db:        ## рапорты -> DuckDB и SQL-витрины
	uv run python src/volve/build_db.py

notebook:  ## собрать и выполнить ноутбук, обновить графики
	uv run python notebooks/build_notebook.py
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb

marts:     ## CSV для BI
	PYTHONPATH=src uv run python src/volve/export_marts.py
