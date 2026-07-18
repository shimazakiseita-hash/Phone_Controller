from setuptools import find_packages, setup

package_name = 'robocon_bridge'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/bringup.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Seita Shimazaki',
    maintainer_email='shimazakiseita@gmail.com',
    description='ROS2 bridge node for robocon manual robot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mock_node = robocon_bridge.mock_node:main',
            'cmd_vel_to_joy = robocon_bridge.cmd_vel_to_joy:main',
        ],
    },
)
