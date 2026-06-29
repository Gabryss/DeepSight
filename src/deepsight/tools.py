from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolRequirement:
    name: str
    purpose: str
    command: str | None = None
    required: bool = True


MISSION_TOOLS: dict[str, list[ToolRequirement]] = {
    "Core robot middleware": [
        ToolRequirement("ROS 2", "Nodes, topics, TF, actions, bags, lifecycle control.", "ros2"),
        ToolRequirement("Cyclone DDS or Fast DDS", "DDS transport for local robot networks.", None),
        ToolRequirement("Zenoh bridge", "Routed communication over lossy or segmented underground links.", "zenoh-bridge-ros2dds", False),
    ],
    "Network and connectivity": [
        ToolRequirement("ping", "Continuous robot reachability checks.", "ping"),
        ToolRequirement("ssh", "Remote restart, log inspection, and service management.", "ssh"),
        ToolRequirement("iperf3", "Throughput testing before a mission.", "iperf3", False),
        ToolRequirement("tcpdump", "Packet capture when links degrade.", "tcpdump", False),
        ToolRequirement("nmap", "Robot discovery and port checks.", "nmap", False),
    ],
    "Mission observability": [
        ToolRequirement("tf2_tools", "TF tree export and transform sanity checks.", "ros2 run tf2_tools view_frames"),
        ToolRequirement("rqt_graph", "ROS graph inspection.", "rqt_graph", False),
        ToolRequirement("foxglove_bridge", "Point cloud, camera, costmap, path, and diagnostic visualization.", "ros2 launch foxglove_bridge foxglove_bridge_launch.xml", False),
        ToolRequirement("rosbag2", "Record and replay field data.", "ros2 bag"),
    ],
    "Robot health": [
        ToolRequirement("diagnostic_aggregator", "Battery, motors, sensors, compute, and thermal health.", "ros2 topic echo /diagnostics", False),
        ToolRequirement("lm-sensors", "Base station CPU and thermal monitoring.", "sensors", False),
        ToolRequirement("nvtop", "GPU load when perception runs onboard.", "nvtop", False),
    ],
    "Mapping and navigation": [
        ToolRequirement("RViz2", "Local fallback visualization for point clouds, TF, costmaps, and goals.", "rviz2", False),
        ToolRequirement("Nav2", "Goal sending, costmaps, planners, controllers, and recovery behaviors.", None, False),
        ToolRequirement("PCL tools", "Post-process and inspect point clouds.", "pcl_viewer", False),
    ],
    "Post processing": [
        ToolRequirement("rosbag2_py / ros2 bag", "Extract mission data and build reports.", "ros2 bag"),
        ToolRequirement("Python scientific stack", "Offline analysis with numpy, scipy, pandas, and matplotlib.", "python3", False),
        ToolRequirement("CloudCompare", "Manual point-cloud QA and map comparison.", "CloudCompare", False),
    ],
}


def mission_tools_payload() -> list[dict[str, object]]:
    return [
        {
            "category": category,
            "tools": [
                {
                    "name": tool.name,
                    "purpose": tool.purpose,
                    "command": tool.command,
                    "required": tool.required,
                }
                for tool in tools
            ],
        }
        for category, tools in MISSION_TOOLS.items()
    ]
