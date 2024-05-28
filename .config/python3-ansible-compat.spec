# spell-checker:ignore bcond pkgversion buildrequires autosetup PYTHONPATH noarch buildroot bindir sitelib numprocesses clib
# All tests require Internet access
# to test in mock use:  --enable-network --with check
# to test in a privileged environment use:
#   --with check --with privileged_tests
%bcond_with     check
%bcond_with     privileged_tests

Name:           ansible-compat
Version:        VERSION_PLACEHOLDER
Release:        1%{?dist}
Summary:        Ansible-compat library

License:        GPL-3.0-or-later
URL:            https://github.com/ansible/ansible-compat
Source0:        %{pypi_source}

BuildArch:      noarch

BuildRequires:  python%{python3_pkgversion}-devel
%if %{with check}
# These are required for tests:
BuildRequires:  python%{python3_pkgversion}-pytest
BuildRequires:  python%{python3_pkgversion}-pytest-xdist
BuildRequires:  python%{python3_pkgversion}-libselinux
BuildRequires:  git-core
%endif
Requires:       git-core


%description
Ansible-compat.

%prep
%autosetup


%generate_buildrequires
%pyproject_buildrequires


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files ansible_compat


%check
%pyproject_check_import
%if %{with check}
%pytest \
  -v \
  --disable-pytest-warnings \
  --numprocesses=auto \
  test
%endif


%files -f %{pyproject_files}
%license LICENSE
%doc docs/ README.md

%changelog
