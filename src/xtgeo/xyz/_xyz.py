# -*- coding: utf-8 -*-
"""XTGeo xyz module (abstract class)"""

from __future__ import print_function, absolute_import

import abc
import six
import os.path

from xtgeo.common import XTGeoDialog
from xtgeo.xyz import _xyz_io
from xtgeo.xyz import _xyz_roxapi

xtg = XTGeoDialog()
logger = xtg.functionlogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class XYZ(object):
    """Abstract Base class for Points and Polygons in XTGeo, but with
    concrete methods."""

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """Initiate instance"""

        self._df = None
        self._ispolygons = False
        self._xname = 'X_UTME'
        self._yname = 'Y_UTMN'
        self._zname = 'Z_TVDSS'
        self._pname = 'POLY_ID'
        self._mname = 'M_MDEPTH'

        if len(args) >= 1:
            # make instance from file import
            pfile = args[0]
            if isinstance(pfile, str):
                logger.info('Instance from file')
                fformat = kwargs.get('fformat', 'guess')
                self.from_file(pfile, fformat=fformat)

        logger.info('Instance initiated')

    # =========================================================================
    # Import and export
    # =========================================================================

    @abc.abstractmethod
    def from_file(self, pfile, fformat='guess'):
        """Import Points or Polygons from a file.

        Supported import formats (fformat):

        * 'xyz' or 'poi' or 'pol': Simple XYZ format

        * 'zmap': ZMAP line format as exported from RMS (e.g. fault lines)

        * 'guess': Try to choose file format based on extension

        Args:
            pfile (str): Name of file
            fformat (str): File format, see list above

        Returns:
            Object instance (needed optionally)

        Raises:
            OSError: if file is not present or wrong permissions.

        """

        if (os.path.isfile(pfile)):
            pass
        else:
            logger.critical('Not OK file')
            raise os.error

        froot, fext = os.path.splitext(pfile)
        if fformat == 'guess':
            if len(fext) == 0:
                logger.critical('File extension missing. STOP')
                raise SystemExit
            else:
                fformat = fext.lower().replace('.', '')

        if fformat in ['xyz', 'poi', 'pol']:
            _xyz_io.import_xyz(self, pfile)
        elif (fformat == 'zmap'):
            _xyz_io.import_zmap(self, pfile)
        else:
            logger.error('Invalid file format (not supported): {}'
                         .format(fformat))
            raise SystemExit

        return self

    @abc.abstractmethod
    def to_file(self, pfile, fformat='xyz', attributes=None, filter=None,
                wcolumn=None, hcolumn=None, mdcolumn='M_MDEPTH'):
        """Export XYZ (Points/Polygons) to file.

        Args:
            pfile (str): Name of file
            fformat (str): File format xyz/poi/pol / rms_attr /rms_wellpicks
            attributes (list): List of extra columns to export (some formats)
            filter (dict): Filter on e.g. top name(s) with keys TopName
                or ZoneName as {'TopName': ['Top1', 'Top2']}
            wcolumn (str): Name of well column (rms_wellpicks format only)
            hcolumn (str): Name of horizons column (rms_wellpicks format only)
            mdcolumn (str): Name of MD column (rms_wellpicks format only)

        Returns:
            Number of points exported

        Note that the rms_wellpicks will try to output to:

        * HorizonName, WellName, MD  if a MD (mdcolumn) is present,
        * HorizonName, WellName, X, Y, Z  otherwise

        Raises:
            KeyError if filter is set and key(s) are invalid

        """
        if self.dataframe is None:
            ncount = 0
            logger.warning('Nothing to export!')
            return ncount

        if fformat is None or fformat in ['xyz', 'poi', 'pol']:
            # NB! reuse export_rms_attr function, but no attributes
            # are possible
            ncount = _xyz_io.export_rms_attr(self, pfile, attributes=None,
                                             filter=filter)

        elif fformat == 'rms_attr':
            ncount = _xyz_io.export_rms_attr(self, pfile,
                                             attributes=attributes,
                                             filter=filter)
        elif fformat == 'rms_wellpicks':
            ncount = _xyz_io.export_rms_wpicks(self, pfile, hcolumn, wcolumn,
                                               mdcolumn=mdcolumn)

        if ncount == 0:
            logger.warning('Nothing to export!')

        return ncount

    @abc.abstractmethod
    def from_roxar(self, project, name, category, stype='horizons',
                   realisation=0):
        """Load a points/polygons item from a Roxar RMS project.

        The import from the RMS project can be done either within the project
        or outside the project.

        Note that a shortform (for polygons) to::

          import xtgeo
          mypoly = xtgeo.xyz.Polygons()
          mypoly.from_roxar(project, 'TopAare', 'DepthPolys')

        is::

          import xtgeo
          mysurf = xtgeo.polygons_from_roxar(project, 'TopAare', 'DepthPolys')

        Note also that horizon/zone/faults name and category must exists
        in advance, otherwise an Exception will be raised.

        Args:
            project (str or special): Name of project (as folder) if
                outside RMS, og just use the magic project word if within RMS.
            name (str): Name of polygons item
            category (str): For horizons/zones/faults: for example 'DL_depth'
                or use a folder notation on clipboard.

            stype (str): RMS folder type, 'horizons' (default) or 'zones' etc!
            realisation (int): Realisation number, default is 0

        Returns:
            Object instance updated

        Raises:
            ValueError: Various types of invalid inputs.

        """
        stype = stype.lower()
        valid_stypes = ['horizons', 'zones', 'faults', 'clipboard']

        if stype not in valid_stypes:
            raise ValueError('Invalid stype, only {} stypes is supported.'
                             .format(valid_stypes))

        _xyz_roxapi.import_xyz_roxapi(
            self, project, name, category, stype, realisation)

    @abc.abstractmethod
    def to_roxar(self, project, name, category, stype='horizons',
                 realisation=0):
        """Export (store) a points/polygons item to a Roxar RMS project.

        The export to the RMS project can be done either within the project
        or outside the project.

        Note also that horizon/zone name and category must exists in advance,
        otherwise an Exception will be raised.

        Args:
            project (str or special): Name of project (as folder) if
                outside RMS, og just use the magic project word if within RMS.
            name (str): Name of polygons item
            category (str): For horizons/zones/faults: for example 'DL_depth'
            stype (str): RMS folder type, 'horizons' (default), 'zones'
                or 'faults' or 'clipboard'
            realisation (int): Realisation number, default is 0

        Returns:
            Object instance updated

        Raises:
            ValueError: Various types of invalid inputs.

        """

        stype = stype.lower()
        valid_stypes = ['horizons', 'zones', 'faults', 'clipboard']

        if stype not in valid_stypes:
            raise ValueError('Invalid stype, only {} stypes is supported.'
                             .format(valid_stypes))

        _xyz_roxapi.export_xyz_roxapi(
            self, project, name, category, stype, realisation)

    # =========================================================================
    # Get and Set properties
    # =========================================================================

    @abc.abstractproperty
    def nrow(self):
        """NROW"""
        pass

    @abc.abstractproperty
    def dataframe(self):
        """Dataframe"""
        pass

    @dataframe.setter
    def dataframe(self, df):
        pass

    # @abc.abstractmethod
    # def get_carray(self, lname):
    #     """Returns the C array pointer (via SWIG) for a given log.

    #     Type conversion is double if float64, int32 if DISC log.
    #     Returns None of log does not exist.
    #     """
    #     try:
    #         np_array = self._df[lname].values
    #     except Exception:
    #         return None

    #     if self.get_logtype(lname) == 'DISC':
    #         carr = _xyz_lowlevel.convert_np_carr_int(self, np_array)
    #     else:
    #         carr = _xyz_lowlevel.convert_np_carr_double(self, np_array)

    #     return carr
