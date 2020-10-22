#!/usr/bin/env python

from __future__ import print_function

import os
import sys

try:
    from pygccxml import *
except Exception as e:
    print()
    print(e)
    print()
    print('On SL6 try: setup pygccxml v1_9_1  -q p2714b; setup castxml v0_00_00_f20180122')
    print('On SL7 try: setup pygccxml v1_9_1a -q p2715a; setup castxml v0_00_00_f20180122')
    print()
    sys.exit(1)

# TEMPORARY: pygccxml uses "time.clock", which is deprecated.
# We don't have control over this dependency, and all the deprecation
# warnings make it imposssible to see any compiling erros. So for now, 
# inhibit those warning messages
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning) 


# Types that we can assume are already defined, so don't form part of our
# dependency tree.
fundamental_types = ['int', 'float', 'double', 'bool', 'unsigned int',
                     'short', 'short int', 'short unsigned int',
                     'long', 'unsigned long', 'long unsigned int',
                     'long long int', 'char', 'unsigned char',
                     'size_t',
                     'std::string']

def type_to_proxy_type(type):
    if ':' in type and type[:5] != 'std::':
        type = type[type.rfind(':')+1:] # strip off namespaces

#    if type[:5] == 'caf::': return type_to_proxy_type(type[5:])

    if type == 'StandardRecord': return 'SRProxy'

    if type == 'TVector3': return 'TVector3Proxy'
    if type in fundamental_types:
        if type == 'size_t': return 'Proxy<ULong64_t>'
        return 'Proxy<'+type+'>'

    if type[:12] == 'std::vector<':
        elem = type[12:type.find(',')]
        return 'VectorProxy<'+type_to_proxy_type(elem)+'>'

    if '[' in type:
        elem = type[:type.find('[')-1]
        size = int(type[type.find('[')+1:-1])
        return 'ArrayProxy<'+elem+', '+str(size)+'>'

    return type+'Proxy'


def base_class(klass):
    assert len(klass.bases) < 2, 'Support for multiple base classes not implemented'
    if len(klass.bases) == 1:
        return klass.bases[0].related_class
    return None


if len(sys.argv) < 1 or len(sys.argv) > 3:
    print('Usage: parse_xml.py [/path/to/header/outputs/] [/path/to/cxx/outputs/]')
    sys.exit(1)

headerDir = os.getcwd()
if len(sys.argv) >= 2: headerDir = sys.argv[1]
cxxDir = os.getcwd()
if len(sys.argv) >= 3: cxxDir = sys.argv[2]

# Locate the castxml executable
generator_path, generator_name = utils.find_xml_generator()

# Figure out where our source files are
context = os.environ['SBNCODE_DIR']

path = [context, os.environ['ROOT_INC']]

config = parser.xml_generator_configuration_t(
    xml_generator_path=generator_path,
    xml_generator=generator_name,
    include_paths=path,
    # This _Float16 definition is a hack for clang (c7) builds. TODO revisit
    cflags='-std=c++1z -DGEN_FLATRECORD_CONTEXT -D_Float16=short -Wno-unknown-warning-option'#,
#    start_with_declarations='caf::StandardRecord'
    )

print('Reading from', context+'/sbncode/StandardRecord/StandardRecord.h')
decls = parser.parse([context+'/sbncode/StandardRecord/StandardRecord.h'],
                     config)

global_namespace = declarations.get_global_namespace(decls)
ns = global_namespace.namespace('caf')

fundamental_types += [e.name for e in ns.enumerations()]
# fundamental_types += ['Experiment'] # isn't currently within the event:: namespace

# Keep track of which classes we've written out so far, for purposes of
# dependency tracking.
emitted = []

# These ones are already implemented in some way or another, so don't let dependency tracking get hung up on them
for t in fundamental_types:
    emitted += [type_to_proxy_type(t)]
    emitted += ['VectorProxy<'+type_to_proxy_type(t)+'>']


disclaimer = '''// This file was auto-generated by parse_xml.py.
// DO NOT EDIT IT DIRECTLY.
// For documentation of the fields see the regular StandardRecord.h'''

joinFunc = '''
std::string Join(const std::string& a, const std::string& b)
{
  if(a.empty()) return b;
  return a+"."+b;
}
'''

# From this point on everything we print goes to SRProxy.h. Remember to send
# messages for the user to stderr.
sys.stdout = open(headerDir+'/SRProxy.h', 'w')

print(disclaimer)
print()
print('#pragma once')
print()
print('#include "sbncode/CAFAna/StandardRecord/Proxy/BasicTypesProxy.h"')
print()
print('#include "sbncode/StandardRecord/SREnums.h"')
print()
print('#include "TVector3.h"')
print()
print('namespace caf')
print('{')
print()

debug = False

def deps_emitted(klass):
    pt = type_to_proxy_type(klass.name)
    base = base_class(klass)
    if base: base = type_to_proxy_type(base.name)

    if base and base not in emitted:
        if debug: sys.stderr.write('Skipping '+pt+' because of '+base+'\n')
        return False

    # Only accept direct members
    for v in [v for v in klass.variables() if v.parent == klass]: # klass.variables():
        type = type_to_proxy_type(str(v.decl_type))
        if 'ArrayProxy' in type: continue # only support arrays of fundamental type for now
        if type not in emitted:
            if debug: sys.stderr.write('Skipping '+pt+' because of '+type+'\n')
            return False

    return True


def write_srproxy_h(klass):
    base = base_class(klass)
    if base: base = type_to_proxy_type(base.name)

    print('/// Proxy for \\ref', klass.name)
    if base:
        print('class', pt+': public', base)
    else:
        print('class', pt)

    print('{')
    print('public:')
    print('  '+pt+'(TDirectory* d, TTree* tr, const std::string& name, const long& base, int offset);')
    print('  '+pt+'(const '+pt+'&) = delete;')
    print('  '+pt+'(const '+pt+'&&) = delete;')

    print()
    # Only accept direct members
    for v in [v for v in klass.variables() if v.parent == klass]: # klass.variables():
        print('  '+type_to_proxy_type(str(v.decl_type)), v.name+';')

    print('};');
    print()

    if debug: sys.stderr.write('Wrote '+pt+'\n')


while True:
    anyWritten = False
    anySkipped = False

    for klass in ns.classes():
        pt = type_to_proxy_type(klass.name)
        if pt in emitted: continue # Wrote this one already

        if not deps_emitted(klass):
            # Unmet dependencies, come back to it
            anySkipped = True
            continue

        write_srproxy_h(klass)

        anyWritten = True
        emitted += [pt]
        emitted += ['VectorProxy<'+pt+'>']

    if not anySkipped: break # We're done
    if anyWritten: continue # Try for some more

    if not debug:
        # Go round one more time to provide feedback
        debug = True
    else:
        sys.stderr.write('Unable to meet all dependencies\n')
        sys.exit(1)

print('} // end namespace')



# And now we're writing to SRProxy.cxx
sys.stdout = open(cxxDir+'/SRProxy.cxx', 'w')
print(disclaimer)
print()
print('#include "sbncode/CAFAna/StandardRecord/Proxy/SRProxy.h"')
print()
#print '#include "sbncode/CAFAna/StandardRecord/StandardRecord.h" // for CheckAgainst'
print()
print('namespace caf{')
print(joinFunc)

# No need to specifically order the functions in the cxx file
for klass in ns.classes():
    pt = type_to_proxy_type(klass.name)
    # Constructor
    print(pt+'::'+pt+'(TDirectory* d, TTree* tr, const std::string& name, const long& base, int offset)')
    # Initializer list
    inits = []
    if base_class(klass): inits += [type_to_proxy_type(base_class(klass).name)+'(d, tr, name, base, offset)']
    # Only accept direct members
    for v in [v for v in klass.variables() if v.parent == klass]: # klass.variables():
        inits += [v.name + '(d, tr, Join(name, "'+v.name+'"), base, offset)']

    if len(inits) > 0:
        print('  : '+',\n    '.join(inits))
    print('{\n}\n')

print('} // namespace')


# Now the CheckEquals() functions
sys.stdout = open(headerDir+'/CheckEquals.h', 'w')
print(disclaimer)
print()
print('#pragma once')
print()
print('#include <vector>')
print()
print('#include "RtypesCore.h"')
print()
print('namespace caf{')
for klass in []: # HACK - was ns.classes():
    pt = type_to_proxy_type(klass.name)
    print('class '+klass.name+';')
    print('class '+pt+';')
    print('void CheckEquals(const '+pt+'& srProxy, const '+klass.name+'& sr);')
    print()
print('''
template<class T> class Proxy;
template<class T> void CheckEquals(const Proxy<T>& x, const T& y);
void CheckEquals(const Proxy<ULong64_t>& x, const size_t& y);

template<class T> class VectorProxy;
template<class T, class U> void CheckEquals(const VectorProxy<T>& x,
                                            const std::vector<U>& y);

template<class T, unsigned int N> class ArrayProxy;
template<class T, unsigned int N> void CheckEquals(const ArrayProxy<T, N>& x,
                                                   const T* y);
''')
print('} // namespace')


sys.stdout = open(cxxDir+'/CheckEquals.cxx', 'w')
print(disclaimer)
print()
print('#include "sbncode/CAFAna/StandardRecord/Proxy/CheckEquals.h"')
print()
print('#include "sbncode/CAFAna/StandardRecord/Proxy/SRProxy.h"')
#print '#include "sbncode/CAFAna/StandardRecord/StandardRecord.h"'
print()
print('#include <type_traits>')
print()
print('namespace caf{')

# Pull this out as a function since we want to recurse into base classes
def check_equals_body(klass):
    # Only accept direct members
    for v in [v for v in klass.variables() if v.parent == klass]: # klass.variables():
        print('  CheckEquals(srProxy.'+v.name+', sr.'+v.name+');')
    if base_class(klass):
        check_equals_body(base_class(klass))

for klass in []: # HACK - was ns.classes():
    pt = type_to_proxy_type(klass.name)
    print('void CheckEquals(const '+pt+'& srProxy, const '+klass.name+'& sr)')
    print('{')
    check_equals_body(klass)
    print('}\n')

print('''
template<class T>
typename std::enable_if<!std::is_floating_point<T>::value, bool>::type
AreEqual(T x, T y)
{
  return x == y;
}

template<class T>
typename std::enable_if<std::is_floating_point<T>::value, bool>::type
AreEqual(T x, T y)
{
  return x == y || (isnan(x) && isnan(y));
}

template<class T> void CheckEquals(const Proxy<T>& x, const T& y)
{
  if(!AreEqual(x.GetValue(), y)){
    std::cout << x.Name() << " differs: "
              << x.GetValue() << " vs " << y << std::endl;
  }
}

void CheckEquals(const Proxy<ULong64_t>& x, const size_t& y)
{
  CheckEquals(x, ULong64_t(y));
}

template<class T, class U> void CheckEquals(const VectorProxy<T>& x,
                                            const std::vector<U>& y)
{
  if(x.size() != y.size()){
    std::cout << x.Name() << ".size() differs. "
              << x.size() << " vs " << y.size() << std::endl;
  }

  for(unsigned int i = 0; i < std::min(x.size(), y.size()); ++i)
    CheckEquals(x[i], y[i]);
}

template<class T, unsigned int N> void CheckEquals(const ArrayProxy<T, N>& x,
                                                   const T* y)
{
  for(unsigned int i = 0; i < N; ++i) CheckEquals(x[i], y[i]);
}
''')
print()
print('} // namespace')

# And CopyRecord() functions
sys.stdout = open(headerDir+'/CopyRecord.h', 'w')
print(disclaimer)
print()
print('#pragma once')
print()
print('#include <vector>')
print()
print('#include "RtypesCore.h"')
print()
print('namespace caf{')
for klass in []: # HACK - was ns.classes():
    pt = type_to_proxy_type(klass.name)
    print('class '+klass.name+';')
    print('class '+pt+';')
    print('void CopyRecord(const '+klass.name+"& from, "+pt+'& to);')
    print()
print('''
template<class T> class Proxy;
template<class T> void CopyRecord(const T& from, Proxy<T>& to);
void CopyRecord(const size_t& from, Proxy<ULong64_t>& to);

template<class T> class VectorProxy;
template<class T, class U> void CopyRecord(const std::vector<U>& from,
                                           VectorProxy<T>& to);

template<class T, unsigned int N> class ArrayProxy;
template<class T, unsigned int N> void CopyRecord(const T* from,
                                                  ArrayProxy<T, N>& to);
''')
print('} // namespace')


sys.stdout = open(cxxDir+'/CopyRecord.cxx', 'w')
print('#include "sbncode/CAFAna/StandardRecord/Proxy/CopyRecord.h"')
print()
print('#include "sbncode/CAFAna/StandardRecord/Proxy/SRProxy.h"')
#print '#include "sbncode/CAFAna/StandardRecord/StandardRecord.h"'
print(disclaimer)
print('namespace caf{')

# Pull this out as a function since we want to recurse into base classes
def copy_body(klass):
    # Only accept direct members
    for v in [v for v in klass.variables() if v.parent == klass]: # klass.variables():
        print('  CopyRecord(from.'+v.name+', to.'+v.name+');')
    if base_class(klass):
        copy_body(base_class(klass))

for klass in []: # HACK - was ns.classes():
    pt = type_to_proxy_type(klass.name)
    print('void CopyRecord(const '+klass.name+"& from, "+pt+'& to)')
    print('{')
    copy_body(klass)
    print('}\n')

print('''
template<class T> void CopyRecord(const T& from, Proxy<T>& to)
{
  to = from;
}

void CopyRecord(const size_t& from, Proxy<ULong64_t>& to)
{
  to = from;
}

template<class T, class U> void CopyRecord(const std::vector<U>& from,
                                           VectorProxy<T>& to)
{
  to.resize(from.size());
  for(unsigned int i = 0; i < from.size(); ++i) CopyRecord(from[i], to[i]);
}

template<class T, unsigned int N> void CopyRecord(const T* from,
                                                  ArrayProxy<T, N>& to)
{
  for(unsigned int i = 0; i < N; ++i) CopyRecord(from[i], to[i]);
}
''')


print('} // namespace')

sys.stderr.write('Wrote SRProxy.cxx, SRProxy.h, CheckEquals.cxx, CheckEquals.h, CopyRecord.cxx, CopyRecord.h\n')
