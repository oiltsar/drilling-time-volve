.PHONY: all db report notebook

all: db report notebook

db:        ## рапорты -> DuckDB и SQL-витрины
	uv run python src/volve/build_db.py

report:    ## графики и CSV для BI
	PYTHONPATH=src uv run python src/volve/report.py

notebook:  ## собрать и выполнить ноутбук
	uv run python notebooks/build_notebook.py
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb
