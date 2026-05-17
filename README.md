# PyLiSuM: Python Middleware for LISA+<sup>®</sup> Traffic Signal Control in SUMO

[![CI](https://github.com/TU-Dresden-VPA/PyLiSuM/actions/workflows/ci.yml/badge.svg)](https://github.com/TU-Dresden-VPA/PyLiSuM/actions/workflows/ci.yml)

PyLiSuM is a Python-based middleware tool for running DACH-style <a href="https://www.schlothauer.de/en/software-lisa" target="_blank" rel="noopener noreferrer">LISA+<sup>®</sup></a> traffic signal control programs in SUMO simulations.

Development of PyLiSuM was supported by Work Package 5, "Upgrading of the Infrastructure", within the project <a href="https://absolut-project.com/" target="_blank" rel="noopener noreferrer">ABSOLUT II</a>, "Autonomous On-Demand Shuttles Providing Individual Public Transport Services for the Suburban Areas of Leipzig". ABSOLUT II is funded by the Bundesministerium für Forschung, Technologie und Raumfahrt der Bundesrepublik Deutschland (BMFTR; Federal Ministry of Research, Technology and Space of Germany) under Grant No. 01ME23001B.

## Requirements

- Java 8 (JDK or JRE)
- Python 3.10 or newer
- SUMO 1.22 or newer

### Java 8 Installation

Java 8 for Windows can be downloaded from the <a href="https://adoptium.net/temurin/releases?version=8&os=any&arch=any" target="_blank" rel="noopener noreferrer">Adoptium Temurin releases page</a>.

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

This repository includes an example simulation for a loop-detector-actuated signalised intersection in Leipzig, Germany. After activating the Python environment, start the simulation as follows:

```bash
python example_simulation.py
```

This example demonstrates the simulation workflow using PyLiSuM.

---

## Notes

PyLiSuM supports multi-intersection simulations. Currently, this repository includes LISA+<sup>®</sup> files for only one intersection. Users must provide additional provisioning files for multi-intersection SUMO simulations.

All raw traffic data and files were processed within the framework of the ABSOLUT II project. They are owned and prepared by the Mobilitäts- und Tiefbauamt (MTA; Mobility and Civil Engineering Office) of the City of Leipzig and may be removed from this repository in the future without notice.

---

## Third-Party Components

This repository includes OMLFGServer binaries required for running LISA+<sup>®</sup> signal control logic. These files were obtained from the public <a href="https://github.com/maxidigital/LisumExamples/tree/master" target="_blank" rel="noopener noreferrer">maxidigital/LisumExamples</a> repository, which is referenced from the <a href="https://sumo.dlr.de/docs/Tools/LiSuM.html" target="_blank" rel="noopener noreferrer">SUMO documentation</a>.

OMLFGServer is third-party software and is not developed or maintained by the PyLiSuM project team. All rights in OMLFGServer and related binary files remain with their respective owners. PyLiSuM uses OMLFGServer only as an external runtime component.

---

## Contributors

See [CONTRIBUTORS.md](CONTRIBUTORS.md).

---

## License

This project is licensed for academic and non-commercial use only. See [LICENSE](LICENSE) for details.
