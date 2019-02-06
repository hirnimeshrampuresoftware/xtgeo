# -*- coding: utf-8 -*-
"""Module for a 3D grid property.

The grid property instances may or may not belong to a grid geometry
object. Normally the instance is created when importing a grid
property from file, but it can also be created directly, as e.g.::

 poro = GridProperty(ncol=233, nrow=122, nlay=32)

The grid property values `someinstance.values` by themselves are 3D masked
numpy as either float64 (double) or int32 (if discrete), and undefined
cells are displayed as masked. The array order is now C_CONTIGUOUS.
(i.e. not in Eclipse manner). A 1D view (C order) is achieved by the
values1d property, e.g.::

 poronumpy = poro.values1d

"""
from __future__ import print_function, absolute_import

import os.path
import copy

import numpy as np
import numpy.ma as ma  # pylint: disable=useless-import-alias

import xtgeo.cxtgeo.cxtgeo as _cxtgeo

import xtgeo
from xtgeo.common.exceptions import DateNotFoundError, KeywordFoundNoDateError
from xtgeo.common.exceptions import KeywordNotFoundError

from xtgeo.common import XTGeoDialog
from xtgeo.common import XTGDescription
from xtgeo.common import _get_fhandle
from xtgeo.grid3d import Grid3D
from xtgeo.grid3d import _gridprop_op1
from xtgeo.grid3d import _gridprop_import
from xtgeo.grid3d import _gridprop_roxapi
from xtgeo.grid3d import _gridprop_export

xtg = XTGeoDialog()
logger = xtg.functionlogger(__name__)

# pylint: disable=logging-format-interpolation, too-many-public-methods

# =============================================================================
# Functions outside the class, for rapid access. Will be exposed as
# xxx = xtgeo.gridproperty_from_file. pylint: disable=fixme
# =============================================================================


def gridproperty_from_file(pfile, fformat='guess', name='unknown',
                           grid=None, date=None):
    """Make a GridProperty instance directly from file import.

    For arguments, see :func:`GridProperty.from_file()`

    Args:
        pfile (str): Property file
        kwargs: See :func:`GridProperty.from_file()`.

    Example::

        import xtgeo
        myporo = xtgeo.gridproperty_from_file('myporofile.roff')
    """

    obj = GridProperty()
    obj.from_file(pfile, fformat=fformat, name=name, grid=grid, date=date)

    return obj


def gridproperty_from_roxar(project, gname, pname, realisation=0):

    """Make a GridProperty instance directly inside RMS.

    For arguments, see :func:`GridProperty.from_roxar()`

    Example::

        import xtgeo
        myporo = xtgeo.gridproperty_from_roxar(project, 'Geogrid', 'Poro')

    """
    obj = GridProperty()
    obj.from_roxar(project, gname, pname, realisation=realisation)

    return obj


# =============================================================================
# GridProperty class
# =============================================================================

class GridProperty(Grid3D):
    """Class for a single 3D grid property, e.g porosity or facies.

    An instance may or may not 'belong' to a grid (geometry) object. E.g. for
    for ROFF, ncol, nrow, nlay are given in the import file.

    The numpy array representing the values is a 3D masked numpy.

    Args:
        ncol (int): Number of columns.
        nrow (int): Number of rows.
        nlay (int): Number of layers.
        values (numpy): A 3D masked numpy of shape (ncol, nrow, nlay).
        name (str): Name of property.
        discrete (bool): True if discrete property
            (default is false).

    Alternatively, the same arguments as the from_file() method
    can be used.

    Returns:
        A GridProperty object instance.

    Raises:
        RuntimeError: if something goes wrong (e.g. file not found)

    Examples::

        from xtgeo.grid3d import GridProperty
        myprop = GridProperty()
        myprop.from_file('emerald.roff', name='PORO')

        # or

        values = ma.ones((12, 17, 10), dtype=np.float64),
        myprop = GridProperty(ncol=12, nrow=17, nlay=10,
                              values=values, discrete=False,
                              name='MyValue')

        # or

        myprop = GridProperty('emerald.roff', name='PORO')


    """

    def __init__(self, *args, **kwargs):

        super(GridProperty, self).__init__(*args, **kwargs)

        ncol = kwargs.get('ncol', 5)
        nrow = kwargs.get('nrow', 12)
        nlay = kwargs.get('nlay', 2)
        values = kwargs.get('values', None)
        name = kwargs.get('name', 'unknown')
        date = kwargs.get('date', None)
        discrete = kwargs.get('discrete', False)
        grid = kwargs.get('grid', None)

        self._ncol = ncol
        self._nrow = nrow
        self._nlay = nlay

        self._isdiscrete = discrete

        # this is a link to the Grid instance, _only if needed_. It may
        # potentially make trouble for garbage collection
        self._geometry = None

        testmask = False
        if values is None:
            values = ma.zeros((ncol, nrow, nlay))
            values += 99
            testmask = True

        if values.shape != (ncol, nrow, nlay):
            values = values.reshape((ncol, nrow, nlay), order='C')

        if not isinstance(values, ma.MaskedArray):
            values = ma.array(values)

        self._values = values       # numpy version of properties (as 3D array)

        self._name = name           # property name
        self._date = None           # property may have an assosiated date
        self._codes = {}            # code dictionary (for discrete)
        self._filesrc = None

        self._undef = _cxtgeo.UNDEF
        self._undef_limit = _cxtgeo.UNDEF_LIMIT

        self._undef_i = _cxtgeo.UNDEF_INT
        self._undef_ilimit = _cxtgeo.UNDEF_INT_LIMIT
        self._actnum_indices = None

        self._roxorigin = False  # true if the object comes from the ROXAPI

        self._roxar_dtype = np.float32
        if self._isdiscrete:
            self._values = self._values.astype(np.int32)
            self._roxar_dtype = np.uint8

        if testmask:
            # make some undef cells (for test)
            self._values[0:4, 0, 0:2] = self._undef
            # make it masked
            self._values = ma.masked_greater(self._values, self._undef_limit)

        if len(args) == 1:
            # make instance through file import

            logger.debug('Import from file...')
            fformat = kwargs.get('fformat', 'guess')
            name = kwargs.get('name', 'unknown')
            date = kwargs.get('date', None)
            grid = kwargs.get('grid', None)
            self.from_file(args[0], fformat=fformat, name=name,
                           grid=grid, date=date)

    def __del__(self):
        logger.info('DELETING property instance %s', self.name)
        self._values = None
        for myvar in vars(self).keys():
            del myvar

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def name(self):
        """Returns or rename the property name."""
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def dimensions(self):
        """3-tuple: The grid dimensions as a tuple of 3 integers (read only)"""
        return (self._ncol, self._nrow, self._nlay)

    @property
    def nactive(self):
        """int: Returns the number of active cells (read only)."""
        return len(self.actnum_indices)

    @property
    def geometry(self):
        """Returns or set the linked geometry, i.e. the Grid instance)
        """
        return self._geometry

    @geometry.setter
    def geometry(self, geom):

        if geom is None:
            self._geometry = None
        elif (isinstance(geom, xtgeo.grid3d.Grid) and
              geom.dimensions == self.dimensions):
            self._geometry = geom
        else:
            raise ValueError('Could not set geometry; wrong type or size')

    @property
    def actnum_indices(self):
        """Returns the 1D ndarray which holds the indices for active cells
        given in 1D, C order (read only).

        """
        actnumv = self.get_actnum()
        actnumv = np.ravel(actnumv.values)
        self._actnum_indices = np.flatnonzero(actnumv)

        return self._actnum_indices

    @property
    def isdiscrete(self):
        """Return True if property is discrete.

        This can also be used to convert from continuous to discrete
        or from discrete to continuous::

            myprop.isdiscrete = False
        """

        return self._isdiscrete

    @isdiscrete.setter
    def isdiscrete(self, flag):

        if not isinstance(flag, bool):
            raise ValueError('Input to {__name__} must be a bool')

        if flag is self._isdiscrete:
            pass
        else:
            if flag is True and self._isdiscrete is False:
                self.continuous_to_discrete()
            else:
                self.discrete_to_continuous()

    @property
    def dtype(self):
        """Return or set the values numpy dtype.

        When setting, note that the the dtype must correspond to the
        `isdiscrete` property.
        """
        return self._values.dtype

    @dtype.setter
    def dtype(self, dtype):
        allowedfloat = [np.float16, np.float32, np.float64]
        allowedint = [np.uint8, np.uint16, np.int16, np.int32, np.int64]

        okv = True
        if self.isdiscrete:
            if dtype in allowedint:
                self.values = self.values.astype(dtype)
            else:
                okv = False
                msg = ('{}: Wrong input for dtype. Use one of {}!'
                       .format(__name__, allowedint))
        else:
            if dtype in allowedfloat:
                self.values = self.values.astype(dtype)
            else:
                okv = False
                msg = ('{}: Wrong input for dtype. Use one of {}!'
                       .format(__name__, allowedfloat))

        if not okv:
            raise ValueError(msg)

    @property
    def filesrc(self):
        """Return or set file src (if any)"""
        return self._filesrc

    @filesrc.setter
    def filesrc(self, src):
        self._filesrc = src

    @property
    def roxar_dtype(self):
        """Return or set the roxar dtype (if any)"""
        return self._roxar_dtype

    @roxar_dtype.setter
    def roxar_dtype(self, dtype):
        allowed = [np.uint16, np.uint8, np.float32]
        if dtype in allowed:
            self._roxar_dtype = dtype
        else:
            raise ValueError('{}: Wrong input for roxar_dtype. Use one of {}!'
                             .format(__name__, allowed))

    @property
    def date(self):
        """Returns or rename the property date on YYYYMMDD numerical format."""
        return self._date

    @date.setter
    def date(self, date):
        self._date = date

    @property
    def codes(self):
        """The property codes as a dictionary."""
        return self._codes

    @codes.setter
    def codes(self, cdict):
        self._codes = cdict.copy()

    @property
    def ncodes(self):
        """Number of codes if discrete grid property (read only)."""
        return len(self._codes)

    @property
    def values(self):
        """ Return or set the grid property as a masked 3D numpy array"""
        return self._values

    @values.setter
    def values(self, values):
        if (isinstance(values, np.ndarray) and
                not isinstance(values, ma.MaskedArray)):

            values = ma.array(values)
            values = values.reshape((self._ncol, self._nrow, self._nlay))

        elif isinstance(values, ma.MaskedArray):
            values = values.reshape((self._ncol, self._nrow, self._nlay))
        else:
            raise ValueError('Problems with values in {}'.format(__name__))

        self._values = values

        trydiscrete = False
        if 'int' in str(values.dtype):
            trydiscrete = True

        if trydiscrete is not self._isdiscrete:
            if trydiscrete:
                self.continuous_to_discrete()
            else:
                self.discrete_to_continuous()

        logger.debug('Values shape: %s', self._values.shape)
        logger.debug('Flags: %s', self._values.flags.c_contiguous)

    @property
    def ntotal(self):
        """Returns total number of cells ncol*nrow*nlay (read only)"""
        return self._ncol * self._nrow * self._nlay

    @property
    def roxorigin(self):
        """Returns True if the property comes from ROXAPI"""
        return self._roxorigin

    @roxorigin.setter
    def roxorigin(self, val):
        if isinstance(val, bool):
            self._roxorigin = val
        else:
            raise ValueError('Input to roxorigin must be True or False')

    @property
    def values3d(self):
        """For backward compatibility (use values instead)"""
        return self._values

    @values3d.setter
    def values3d(self, values):
        # kept for backwards compatibility
        self.values = values

    @property
    def values1d(self):
        """Returns a 1D view of values (masked numpy) (read only)."""
        return self._values.reshape(-1)

    @property
    def undef(self):
        """Get the actual undef value for floats or ints
        numpy arrays (read only).
        """
        if self._isdiscrete:
            return self._undef_i

        return self._undef

    @property
    def undef_limit(self):
        """Returns the undef limit number, which is slightly less than the
        undef value.

        Hence for numerical precision, one can force undef values
        to a given number, e.g.::

           x[x<x.undef_limit]=999

        Undef limit values cannot be changed (read only).

        """
        if self._isdiscrete:
            return self._undef_ilimit

        return self._undef_limit

    # =========================================================================
    # Various public methods
    # =========================================================================
    def describe(self):
        """Describe an instance by printing to stdout"""

        dsc = XTGDescription()
        dsc.title('Description of GridProperty instance')
        dsc.txt('Object ID', id(self))
        dsc.txt('Name', self.name)
        dsc.txt('Date', self.date)
        dsc.txt('File source', self._filesrc)
        dsc.txt('Discrete status', self._isdiscrete)
        dsc.txt('Codes', self._codes)
        dsc.txt('Shape: NCOL, NROW, NLAY', self.ncol, self.nrow, self.nlay)
        np.set_printoptions(threshold=16)
        dsc.txt('Values', self._values.reshape(-1), self._values.dtype)
        np.set_printoptions(threshold=1000)
        dsc.txt('Values, mean, stdev, minimum, maximum', self.values.mean(),
                self.values.std(), self.values.min(), self.values.max())
        itemsize = self.values.itemsize
        msize = float(self.values.size * itemsize) / (1024 * 1024 * 1024)
        dsc.txt('Roxar datatype', self.roxar_dtype)
        dsc.txt('Minimum memory usage of array (GB)', msize)

        dsc.flush()

    def get_npvalues3d(self, fill_value=None):
        """Get a pure numpy copy (not masked) copy of the values, 3D shape.

        Note that Numpy dtype will be reset; int32 if discrete or float64 if
        continuous. The reason for this is to avoid inconsistensies regarding
        UNDEF values.

        Args:
            fill_value: Value of masked entries. Default is None which
                means the XTGeo UNDEF value (a high number), different
                for a continuous or discrete property
        """
        # this is a function, not a property by design

        if fill_value is None:
            if self._isdiscrete:
                fvalue = _cxtgeo.UNDEF_INT
                dtype = np.int32
            else:
                fvalue = _cxtgeo.UNDEF
                dtype = np.float64
        else:
            fvalue = fill_value
            dtype = np.float64

        val = self.values.copy().astype(dtype)
        npv3d = ma.filled(val, fill_value=fvalue)
        del val

        return npv3d

    def get_actnum(self, name='ACTNUM', mask=False):
        """Return an ACTNUM GridProperty object.

        Args:
            name (str): name of property in the XTGeo GridProperty object.
            mask (bool): Opposite to most, actnum is returned will all cells
                as default. Use mask=True to make 0 entries masked.

        Example::

            act = myprop.get_actnum()
            print('{}% cells are active'.format(act.values.mean() * 100))
        """

        act = GridProperty(ncol=self._ncol, nrow=self._nrow,
                           nlay=self._nlay,
                           name=name, discrete=True)

        orig = self.values
        vact = np.ones(self.values.shape)
        print(vact)
        vact[orig.mask] = 0
        print(vact)

        if mask:
            vact = ma.masked_equal(vact, 0)

        act.values = vact.astype(np.int32)
        act.codes = {0: '0', 1: '1'}

        # return the object
        return act

    def get_active_npvalues1d(self):
        """Return the grid property as a 1D numpy array (copy), active
        cells only.
        """
        vact = self.values1d.copy()
        vact = vact[~vact.mask]
        return np.array(vact)

    def copy(self, newname=None):
        """Copy a xtgeo.grid3d.GridProperty() object to another instance.

        ::

            >>> mycopy = xx.copy(newname='XPROP')
        """

        if newname is None:
            newname = self.name

        xprop = GridProperty(ncol=self._ncol, nrow=self._nrow, nlay=self._nlay,
                             values=self._values.copy(), name=newname)

        xprop.geometry = self._geometry
        xprop.codes = copy.deepcopy(self._codes)
        xprop.isdiscrete = self._isdiscrete
        xprop.date = self._date
        xprop.roxorigin = self._roxorigin
        xprop.roxar_dtype = self._roxar_dtype

        if self._filesrc is not None and '(copy)' not in self._filesrc:
            xprop.filesrc = self._filesrc + ' (copy)'
        elif self._filesrc is not None:
            xprop.filesrc = self._filesrc

        return xprop

    def mask_undef(self):
        """Make UNDEF values masked."""
        if self._isdiscrete:
            self._values = ma.masked_greater(self._values, self._undef_ilimit)
        else:
            self._values = ma.masked_greater(self._values, self._undef_limit)

    def crop(self, spec):
        """Crop a property, see method under grid"""

        (ic1, ic2), (jc1, jc2), (kc1, kc2) = spec

        # compute size of new cropped grid
        self._ncol = ic2 - ic1 + 1
        self._nrow = jc2 - jc1 + 1
        self._nlay = kc2 - kc1 + 1

        newvalues = self.values.copy()

        self.values = newvalues[ic1 - 1: ic2, jc1 - 1: jc2, kc1 - 1: kc2]

    # =========================================================================
    # Import and export
    # =========================================================================

    def from_file(self, pfile, fformat='guess', name='unknown',
                  grid=None, date=None, _roffapiv=1):  # _roffapiv for devel.
        """
        Import grid property from file, and makes an instance of this class.

        Note that the the property may be linked to its geometrical grid,
        through the grid= option. Sometimes this is required, for instance
        for most Eclipse input.

        Args:
            pfile (str): name of file to be imported
            fformat (str): file format to be used roff/init/unrst
                (guess is default).
            name (str): name of property to import
            date (int or str): For restart files, date on YYYYMMDD format. Also
                the YYYY-MM-DD form is allowed (string), and for Eclipse,
                mnemonics like 'first', 'last' is also allowed.
            grid (Grid object): Grid Object for checks (optional for ROFF,
                required for Eclipse).

        Examples::

           x = GridProperty()
           x.from_file('somefile.roff', fformat='roff')
           #
           mygrid = Grid('ECL.EGRID')
           pressure_1 = GridProperty()
           pressure_1.from_file('ECL.UNRST', name='PRESSURE', date='first',
                                grid=mygrid)

        Returns:
           True if success, otherwise False
        """

        # pylint: disable=too-many-branches, too-many-statements

        self._filesrc = pfile

        # it may be that pfile already is an open file; hence a filehandle
        # instead. Check for this, and skip tests of so
        pfile_is_not_fhandle = True
        _fhandle, pclose = _get_fhandle(pfile)
        if not pclose:
            pfile_is_not_fhandle = False

        if pfile_is_not_fhandle:
            if os.path.isfile(pfile):
                logger.debug('File {} exists OK'.format(pfile))
            else:
                logger.critical('No such file: {}'.format(pfile))
                raise IOError

            # work on file extension
            _froot, fext = os.path.splitext(pfile)
            if fformat == 'guess':
                if not fext:
                    logger.critical('File extension missing. STOP')
                    raise ValueError('File extension missing. STOP')
                else:
                    fformat = fext.lower().replace('.', '')

            logger.debug("File name to be used is {}".format(pfile))
            logger.debug("File format is {}".format(fformat))

        ier = 0
        if fformat == 'roff':
            logger.info('Importing ROFF...')
            ier = _gridprop_import.import_roff(self, pfile, name, grid=grid,
                                               _roffapiv=_roffapiv)

        elif fformat.lower() == 'init':
            ier = _gridprop_import.import_eclbinary(self, pfile, name=name,
                                                    etype=1, date=None,
                                                    grid=grid)

        elif fformat.lower() == 'unrst':
            if date is None:
                raise ValueError('Restart file, but no date is given')
            elif isinstance(date, str):
                if '-' in date:
                    date = int(date.replace('-', ''))
                elif date == 'first':
                    date = 0
                elif date == 'last':
                    date = 9
                else:
                    date = int(date)

            ier = _gridprop_import.import_eclbinary(self, pfile, name=name,
                                                    etype=5, date=date,
                                                    grid=grid)
        else:
            logger.warning('Invalid file format')
            raise SystemExit('Invalid file format')

        if ier == 22:
            raise DateNotFoundError('Date {} not found when importing {}'
                                    .format(date, name))
        elif ier == 23:
            raise KeywordNotFoundError('Keyword {} not found for date {} '
                                       'when importing'.format(name, date))
        elif ier == 24:
            raise KeywordFoundNoDateError('Keyword {} found but not for date '
                                          '{} when importing'
                                          .format(name, date))
        elif ier == 25:
            raise KeywordNotFoundError('Keyword {} not found when importing'
                                       .format(name))
        elif ier != 0:
            raise RuntimeError('Something went wrong, code {}'.format(ier))

        # if grid, then append this grid to the current grid object
        if grid:
            grid.append_prop(self)

        return self

    def from_roxar(self, projectname, gname, pname, realisation=0):

        """Import grid model property from RMS project, and makes an instance.

        Arguments:
            projectname (str): Name of RMS project; use pure 'project'
                if inside RMS
            gfile (str): Name of grid model
            pfile (str): Name of grid property
            projectname (str): Name of RMS project; None if within a project
            realisation (int): Realisation number (default 0 first)

        """

        self._filesrc = ('ROXAR API GridModel:{} Property: {}'
                         .format(gname, pname))

        _gridprop_roxapi.import_prop_roxapi(
            self, projectname, gname, pname, realisation)

    def to_roxar(self, projectname, gname, pname, saveproject=False,
                 realisation=0):

        """Store a grid model property into a RMS project.

        Arguments:
            projectname (str): Name of RMS project ('project' if inside a
                RMS project)
            gfile (str): Name of grid model
            pfile (str): Name of grid property
            projectname (str): Name of RMS project (None if inside a project)
            saveproject (bool): If True, a saveproject job will be ran.
            realisation (int): Realisation number (default 0 first)

        """
        _gridprop_roxapi.export_prop_roxapi(
            self, projectname, gname, pname, saveproject=saveproject,
            realisation=realisation)

    def to_file(self, pfile, fformat='guess', name=None):
        """
        Export grid property to file.

        Args:
            pfile (str): file name
            fformat (str): file format to be used. The default 'guess' is
                roff which is the only supported currently, which is either
                'roff' or 'roff_binary' for binary, and 'roffasc'
                or 'roff_ascii' for ASCII (text).
            name (str): If provided, will give property name; else the existing
                name of the instance will used.
        """
        logger.debug('Export property to file...')

        # guess based on file extension (todo)
        if fformat == 'guess':
            fformat = 'roff'

        if 'roff' in fformat:
            if name is None:
                name = self.name

            binary = True
            if 'asc' in fformat:
                binary = False

            # for later usage
            append = False
            last = True

            _gridprop_export.export_roff(self, pfile, name, append=append,
                                         last=last, binary=binary)

    def get_xy_value_lists(self, grid=None, mask=True):
        """Get lists of xy coords and values for Webportal format.

        The coordinates are on the form (two cells)::

            [[[(x1,y1), (x2,y2), (x3,y3), (x4,y4)],
            [(x5,y5), (x6,y6), (x7,y7), (x8,y8)]]]

        Args:
            grid (object): The XTGeo Grid object for the property
            mask (bool): If true (default), inactive cells will be omitted,
                otherwise cell geometries will be listed and property will
                have value -999 in undefined cells.

        Example::

            grid = Grid()
            grid.from_file('../xtgeo-testdata/3dgrids/bri/b_grid.roff')
            prop = GridProperty()
            prop.from_file('../xtgeo-testdata/3dgrids/bri/b_poro.roff',
                           grid=grid, name='PORO')

            clist, valuelist = prop.get_xy_value_lists(grid=grid, mask=False)


        """

        clist, vlist = _gridprop_op1.get_xy_value_lists(self, grid=grid,
                                                        mask=mask)
        return clist, vlist

    def get_values_by_ijk(self, iarr, jarr, karr, base=1):
        """Get a 1D ndarray of values by I J K arrays.

        This could for instance be a well path where I J K
        exists as well logs.

        Note that the input arrays have 1 as base as default

        Args:
            iarr (ndarray): Numpy array of I
            jarr (ndarray): Numpy array of J
            karr (ndarray): Numpy array of K
            base (int): Should be 1 or 0, dependent on what
                number base the input arrays has.

        Returns:
            pvalues (ndarray): A 1D numpy array of property values,
                with NaN if undefined

        """
        res = np.zeros(iarr.shape, dtype='float64')
        res = ma.masked_equal(res, 0)  # mask all

        # get indices where defined (note the , after valids)
        valids, = np.where(~np.isnan(iarr))

        iarr = iarr[~np.isnan(iarr)]
        jarr = jarr[~np.isnan(jarr)]
        karr = karr[~np.isnan(karr)]

        try:
            res[valids] = self.values[iarr.astype('int') - base,
                                      jarr.astype('int') - base,
                                      karr.astype('int') - base]

            return np.ma.filled(res, fill_value=np.nan)

        except IndexError as ier:
            xtg.warn('Error {}, return None'.format(ier))
            return None
        except:
            xtg.warn('Unexpected error')
            raise

    def discrete_to_continuous(self):
        """Convert from discrete to continuous values"""

        if self.isdiscrete:
            logger.info('Converting to continuous ...')
            val = self._values.copy()
            val = val.astype('float64')
            self._values = val
            self._isdiscrete = False
            self._codes = {}
            self._roxar_dtype = np.float32
        else:
            logger.info('No need to convert, already continuous')

    def continuous_to_discrete(self):
        """Convert from continuous to discrete values"""

        if not self.isdiscrete:
            logger.info('Converting to discrete ...')
            val = self._values.copy()
            val = val.astype(np.int32)
            self._values = val
            self._isdiscrete = True

            # make the code list
            uniq = np.unique(val).tolist()
            codes = dict(zip(uniq, uniq))
            codes = {k: str(v) for k, v in codes.items()}  # val as strings
            self.codes = codes
            self._roxar_dtype = np.uint16
        else:
            logger.info('No need to convert, already discrete')

    # =========================================================================
    # Operations restricted to inside/outside polygons
    # =========================================================================

    def operation_polygons(self, poly, value, opname='add', inside=True):
        """A generic function for doing 3D grid property operations
        restricted to inside or outside polygon(s).

        This method requires that the property geometry is known
        (prop.geometry is set to a grid instance)

        Args:
            grid (Grid): The grid geometry instance
            poly (Polygons): A XTGeo Polygons instance
            value (float): Value to add, subtract etc
            opname (str): Name of operation... 'add', 'sub', etc
            inside (bool): If True do operation inside polygons; else outside.
        """

        if self.geometry is None:
            raise ValueError('The geometry attribute is not set')

        _gridprop_op1.operation_polygons(self, poly, value,
                                         opname=opname, inside=inside)

    # shortforms
    def add_inside(self, poly, value):
        """Add a value (scalar) inside polygons"""
        self.operation_polygons(poly, value, opname='add', inside=True)

    def add_outside(self, poly, value):
        """Add a value (scalar) outside polygons"""
        self.operation_polygons(poly, value, opname='add', inside=False)

    def sub_inside(self, poly, value):
        """Subtract a value (scalar) inside polygons"""
        self.operation_polygons(poly, value, opname='sub', inside=True)

    def sub_outside(self, poly, value):
        """Subtract a value (scalar) outside polygons"""
        self.operation_polygons(poly, value, opname='sub', inside=False)

    def mul_inside(self, poly, value):
        """Multiply a value (scalar) inside polygons"""
        self.operation_polygons(poly, value, opname='mul', inside=True)

    def mul_outside(self, poly, value):
        """Multiply a value (scalar) outside polygons"""
        self.operation_polygons(poly, value, opname='mul', inside=False)

    def div_inside(self, poly, value):
        """Divide a value (scalar) inside polygons"""
        self.operation_polygons(poly, value, opname='div', inside=True)

    def div_outside(self, poly, value):
        """Divide a value (scalar) outside polygons"""
        self.operation_polygons(poly, value, opname='div', inside=False)

    def set_inside(self, poly, value):
        """Set a value (scalar) inside polygons"""
        self.operation_polygons(poly, value, opname='set', inside=True)

    def set_outside(self, poly, value):
        """Set a value (scalar) outside polygons"""
        self.operation_polygons(poly, value, opname='set', inside=False)
