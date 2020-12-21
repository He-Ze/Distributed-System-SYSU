from distutils.core import setup
setup(
  name = 'pmul',
  packages = ['pmul'], # this must be the same as the name above
  version = '0.8',
  description = 'An implementation of the P_MUL protocol in python',
  author = 'Andreas Baessler',
  author_email = 'a_baessler@web.de',
  url = 'https://github.com/baessler/pmul', # use the URL to the github repo
  download_url = 'https://github.com/baessler/pmul/archive/0.8.tar.gz', # I'll explain this in a second
  keywords = ['p_mul', 'pmul', 'transport', 'protocol', 'multicast', 'udp'], # arbitrary keywords
  classifiers = [],
)