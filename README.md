# PyLiSuM

PyLiSuM is a Python-based middleware tool for executing DACH-style LISA+ traffic signal control provisioning files in SUMO simulations. The signal provisioning files are owned by the Mobility and Civil Engineering Office of the City of Leipzig. Therefore, they may be removed from this repository in the future without notice.

## Requirements

- Java 8 (JDK or JRE)
- Python 3.10 or higher
- SUMO 1.22 or higher

### Java 8 Installation

Java 8 for Windows can be downloaded from the [Adoptium Temurin releases page](https://adoptium.net/temurin/releases?version=8&os=any&arch=any).

After downloading:

1. Extract the ZIP archive.
2. Copy the entire contents into the `Java_8/` folder.

---

## Python Dependencies

The following Python packages are required:

- PyYAML
- eclipse-sumo
- psutil
- requests

### Virtual Environment (Recommended)

Using a virtual Python environment is recommended:

```bash
python -m venv .venv
```

### Activate the Environment (Windows)

```bash
.venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Example Simulation

This repository includes an example simulation for a signalised intersection in Leipzig, Germany. After activating the Python environment, the simulation can be started as follows:

```bash
python example_simulation.py
```

This demonstrates the simulation workflow using PyLiSuM.

---

## Notes

Simulating multiple intersections is supported. Currently, LISA+ files are included for only one intersection. Additional provisioning files must be provided by the user for multi-intersection SUMO simulations.
