# PyLiSuM

This middleware enables the establishment of a high-fidelity digital twin for traffic signal control at real-world urban intersections in the DACH region, where LISA+ provisioning files are deployed. The following software and publications form the foundation of this highly functional and extensible middleware:

1. [LiSuM](https://sumo.dlr.de/docs/Tools/LiSuM.html)
2. [LemgoRL](https://github.com/RL-INA/LemgoRL)
3. Barthauer, M., & Friedrich, B. (2017). *Connecting microscopic traffic simulation and LISA+ external signal control*. Transportation Research Procedia, 27, 420–427.
4. Barthauer, M., & Friedrich, B. (2017). *External signal control: Integrating LISA+ into SUMO*. SUMO 2017 – Towards Simulation for Autonomous Mobility, 143.
5. Bottazzi, M., Touko Tcheumadjeu, L. C., Trumpold, J., Erdmann, J., & Oertel, R. (2017). *LiSuM: Design and development of a middleware to couple a virtual LISA+ TLS controller with SUMO simulation*. SUMO 2017 – Towards Simulation for Autonomous Mobility, 31, 179–192.

## ⚠️ Important Notice: Restrictions on LISA+ Provisioning Files and OmlFgServer

Due to infrastructure security constraints, we **cannot permanently use real intersection LISA+ provisioning files** (German: *LISA+ Versorgungsdateien*) for demonstrations. These files will be deleted at an appropriate time.

To **protect intellectual property rights**, we are also unable to provide the OmlFgServer. Please note that the LISA+ `OmlFgServer.jar` is required. This component is a proprietary virtual traffic signal controller server, available for purchase from [**Schlothauer & Wauer GmbH**](https://www.schlothauer.de/en/software-lisa). As an alternative, please refer to the documentation of the German Aerospace Center (DLR) [LiSuM](https://sumo.dlr.de/docs/Tools/LiSuM.html) for guidance on configuring this server.

If you encounter difficulties during configuration, or if you are interested in integrating PyLiSuM with your own signal control algorithms in SUMO simulations, limited voluntary consulting support can be provided.

## License

This project is licensed under the 

[CC BY-NC 4.0 License](https://creativecommons.org/licenses/by-nc/4.0/).

Dieses Projekt ist lizenziert unter der 

Creative Commons Namensnennung – Nicht kommerziell 4.0 International Lizenz ([CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)).

## Acknowledgement

This work is part of the [ABSOLUT II](https://absolut-project.com/) project (*Autonomous On-Demand Shuttles Providing Individual Public Transport Services for Suburban Areas of Leipzig*), funded by the Federal Ministry of Research, Technology and Space of Germany (*Bundesministerium für Forschung, Technologie und Raumfahrt der Bundesrepublik Deutschland*).

We gratefully acknowledge the consultation provided by Dr. Arthur Müller (Fraunhofer IOSB-INA).

--------



