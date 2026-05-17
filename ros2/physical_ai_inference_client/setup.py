from setuptools import find_packages, setup

package_name = 'physical_ai_inference_client'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/config', [
            'config/inference.yaml',
            'config/initial_positions.yaml',
            'config/initial_positions_full.yaml',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='you@example.com',
    description='Send START_INFERENCE commands to a Physical AI server.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'start_inference = physical_ai_inference_client.inference_client:main',
            'test_send_command_server = physical_ai_inference_client.test_send_command_server:main',
            'record_joint_positions = physical_ai_inference_client.record_joint_positions:main',
            'joint_slider_gui = physical_ai_inference_client.joint_slider_gui:main',
        ],
    },
)
