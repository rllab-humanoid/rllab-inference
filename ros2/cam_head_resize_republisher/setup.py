from setuptools import find_packages, setup

package_name = 'cam_head_resize_republisher'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=["test"]),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubless607',
    maintainer_email='leeeesj@postech.ac.kr',
    description='Resize a compressed camera image and republish as compressed JPEG.',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'cam_head_resize_republish = cam_head_resize_republisher.cam_head_resize_republish:main',
        ],
    },
)