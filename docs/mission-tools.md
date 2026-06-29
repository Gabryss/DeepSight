# Underground Mission Tool Checklist

DeepSight assumes a field laptop or base station that can see the robot network and has ROS 2 sourced before robot-specific commands are launched.

## Required Live Tools

- ROS 2 CLI: inspect nodes, topics, services, parameters, actions, bags, and lifecycle state.
- DDS implementation: Cyclone DDS or Fast DDS for normal ROS 2 transport.
- `ping`: background reachability checks for every robot, relay, and base-station host.
- `ssh`: allowlisted remote commands such as service restart, launch scripts, and log collection.
- TF tooling: `tf2_tools` for frame-tree inspection and transform sanity checks.
- ROS bag tooling: record mission data for post processing and incident review.
- Diagnostics topics: battery, compute, motor, sensor, thermal, and network health.

## Strongly Recommended Live Tools

- Zenoh bridge: useful when the underground network is routed, intermittent, or split across relays.
- Foxglove bridge: browser visualization for point clouds, camera feeds, costmaps, paths, markers, and diagnostics.
- RViz2: local fallback visualizer when the web stack is not enough.
- `iperf3`: throughput validation before deployment.
- `tcpdump`: packet capture during link failures.
- `nmap`: host and service discovery.

## Post-Processing Tools

- `ros2 bag`: replay, trim, and inspect mission data.
- Python scientific stack: numpy, scipy, pandas, matplotlib, open3d, and Jupyter for analysis.
- PCL tools: quick point-cloud inspection and conversion.
- CloudCompare: manual map quality inspection and comparison.
- Video/image tools: ffmpeg and OpenCV for camera-feed extraction and QA.

## Mission Data To Track

- Robot connectivity, latency, and packet loss.
- Current middleware mode: DDS or Zenoh.
- ROS graph: nodes, topics, services, actions, and lifecycle state.
- TF tree freshness and missing transforms.
- Topic bandwidth for point clouds, images, costmaps, localization, and diagnostics.
- Battery percentage, voltage, current, and estimated remaining time.
- CPU, GPU, memory, disk, temperature, and process health.
- Navigation state, current goal, planner/controller status, and recovery behavior.
- Map, costmap, point-cloud, camera, and odometry streams.
- Bag recording status and remaining disk capacity.
