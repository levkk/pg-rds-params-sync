import setuptools
from rdsparamsync import VERSION

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='pg-rds-params-sync',
    version=VERSION,
    author='Lev Kokotov',
    author_email='lev.kokotov@instacart.com',
    description="Audit RDS PostgreSQL parameters for drift and compliance.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/levkk/pg-rds-params-sync',
    install_requires=[
        'Click>=7.0',
        'colorama>=0.4.3',
        'prettytable>=0.7.2',
        'psycopg2>=2.8.4',
        'diskcache>=4.1.0',
        'boto3>=1.11.9',
        'tqdm>=4.46.0',
    ],
    extras_require={
        'dev': 'pytest'
    },
    packages=setuptools.find_packages(exclude=('tests',)),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent', # Colorama!
    ],
    python_requires='>=3',
    entry_points={
        'console_scripts': [
            'pgrdsparamsync = rdsparamsync:entrypoint',
        ]
    },
)
