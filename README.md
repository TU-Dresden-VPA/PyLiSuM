# PyLiSuM

PyLiSuM is a Python-based middleware tool for executing DACH-style [LISA+®](https://www.schlothauer.de/en/software-lisa) traffic signal control provisioning files in SUMO simulations.

Development of PyLiSuM was supported by Work Package 5, "Upgrading of the Infrastructure", within the project [ABSOLUT II](https://absolut-project.com/), "Autonomous On-Demand Shuttles Providing Individual Public Transport Services for the Suburban Areas of Leipzig". ABSOLUT II is funded by the Bundesministerium für Forschung, Technologie und Raumfahrt der Bundesrepublik Deutschland (BMFTR; Federal Ministry of Research, Technology and Space of Germany) under Grant No. 01ME23001B.

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

All raw traffic data and files were processed within the framework of the ABSOLUT II project, and are owned and prepared by the Mobilitäts- und Tiefbauamt (MTA; Mobility and Civil Engineering Office) of the City of Leipzig. Therefore, they may be removed from this repository in the future without notice.

---

## Third-Party Components

This repository includes OMLFGServer binaries required for executing LISA+ signal control logic. These files were obtained from the public [maxidigital/LisumExamples](https://github.com/maxidigital/LisumExamples/tree/master) repository, which is referenced from the SUMO documentation.

OMLFGServer is third-party software and is not developed or maintained by the PyLiSuM project team. All rights in OMLFGServer and related binary files remain with their respective owners. PyLiSuM uses OMLFGServer only as an external runtime component.

---

## Contributors

See [CONTRIBUTORS.md](CONTRIBUTORS.md).

---

## License

This project is licensed for academic and non-commercial use only. See [LICENSE](LICENSE) for details.
