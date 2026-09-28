import nbformat
from nbclient import NotebookClient

print("Reading data.ipynb...")
with open("data.ipynb", "r", encoding="utf-8") as f:
    nb = nbformat.read(f, as_version=4)

print("Executing notebook cells...")
client = NotebookClient(nb, timeout=600)
client.execute()

print("Saving executed data.ipynb...")
with open("data.ipynb", "w", encoding="utf-8") as f:
    nbformat.write(nb, f)

print("Successfully executed and saved data.ipynb with all outputs!")
