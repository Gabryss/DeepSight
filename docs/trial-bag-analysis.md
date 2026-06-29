# Mine Nider Trial Bag Analysis

Trial bag root:

```text
/home/gabriel/bag_files/mine_nider
```

Validated bag:

```text
rosbag2_2026_06_02-11_49_55
```

`ros2 bag info` confirms this is a ROS 2 Jazzy MCAP bag with:

- `/leo05/livox/lidar`: `sensor_msgs/msg/PointCloud2`, 316 messages.
- `/leo05/livox/imu`: `sensor_msgs/msg/Imu`, 6323 messages.
- `/tf`: `tf2_msgs/msg/TFMessage`, 3927 messages.
- `/tf_static`: `tf2_msgs/msg/TFMessage`, 1 message.
- `/leo05/cmd_vel`: `geometry_msgs/msg/Twist`, 0 messages.

## What Can Be Visualized From This Bag

- Point cloud playback and inspection.
- IMU stream monitoring.
- TF tree reconstruction and frame sanity checks.
- Timeline and topic/message-count summaries.

## What Cannot Be Fully Monitored From This Bag Alone

The bag does not contain camera, costmap, diagnostics, battery, or network telemetry topics. That means the dashboard can show bag inventory and topic coverage, and a ROS/Foxglove/RViz session can visualize point clouds and TF, but full field monitoring cannot be reconstructed from this bag alone.

For full mission replay, future bags should also record:

- Camera topics.
- Costmap/map topics.
- `/diagnostics`.
- Battery state.
- Network RSSI, link quality, packet loss, and bandwidth telemetry.
- Navigation goals, paths, planner/controller state, and recovery status.
