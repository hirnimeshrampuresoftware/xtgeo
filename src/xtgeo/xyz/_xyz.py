# -*- coding: utf-8 -*-
"""XTGeo XYZ module (abstract base class)"""
from abc import ABC, abstractmethod

import pandas as pd
from xtgeo.common import XTGDescription, XTGeoDialog

xtg = XTGeoDialog()
logger = xtg.functionlogger(__name__)


class XYZ(ABC):
    """Abstract base class for XYZ objects, i.e. Points and Polygons in XTGeo.

    The XYZ base class has common methods and properties for Points and Polygons. The
    underlying data storage is a Pandas dataframe with minimal 3 (Points) or 4
    (Polygons) columns, where the two first represent X and Y coordinates.

    The third column is a number, which may represent the depth, thickness, or other
    property. For Polygons, there is a 4'th column which is an integer representing
    poly-line ID, which is handled in the Polygons class. Similarly, Points and Polygons
    can have additional columns called `attributes`.

    Note:
        You cannot use the XYZ class directly. Use the :class:`Points` or
        :class:`Polygons` classes!
    """

    def __init__(
        self,
        xname: str = "X_UTME",
        yname: str = "Y_UTMN",
        zname: str = "Z_TVDSS",
    ):
        """Concrete initialisation for base class _XYZ."""
        self._xname = xname
        self._yname = yname
        self._zname = zname

    def _reset(
        self,
        xname: str = "X_UTME",
        yname: str = "Y_UTMN",
        zname: str = "Z_TVDSS",
    ):
        """Used in deprecated methods."""
        self._xname = xname
        self._yname = yname
        self._zname = zname

    @property
    def xname(self):
        """Returns or set the name of the X column."""
        return self._xname

    @xname.setter
    def xname(self, newname):
        self._df_column_rename(newname, self._xname)
        self._xname = newname

    @property
    def yname(self):
        """Returns or set the name of the Y column."""
        return self._yname

    @yname.setter
    def yname(self, newname):
        self._df_column_rename(newname, self._yname)
        self._yname = newname

    @property
    def zname(self):
        """Returns or set the name of the Z column."""
        return self._zname

    @zname.setter
    def zname(self, newname):
        self._df_column_rename(newname, self._zname)
        self._zname = newname

    @property
    @abstractmethod
    def dataframe(self) -> pd.DataFrame:
        """Return or set the Pandas dataframe object."""
        ...

    @property
    def nrow(self):
        """Returns the Pandas dataframe object number of rows."""
        if self.dataframe is None:
            return 0
        return len(self.dataframe.index)

    def _df_column_rename(self, newname, oldname):
        if isinstance(newname, str):
            if oldname and self.dataframe is not None:
                self.dataframe.rename(columns={oldname: newname}, inplace=True)
        else:
            raise ValueError(f"Wrong type of input to {newname}; must be string")

    def _check_name(self, value):
        if not isinstance(value, str):
            raise ValueError(f"Wrong type of input; must be string, was {type(value)}")

        if value not in self.dataframe.columns:
            raise ValueError(
                f"{value} does not exist as a column name, must be "
                f"one of: f{self.dataframe.columns}"
            )

    @abstractmethod
    def copy(self):
        """Returns a deep copy of an instance"""
        ...

    def describe(self, flush=True):
        """Describe an instance by printing to stdout"""

        dsc = XTGDescription()
        dsc.title("Description of {} instance".format(self.__class__.__name__))
        dsc.txt("Object ID", id(self))
        dsc.txt("xname, yname, zname", self._xname, self._yname, self._zname)

        if flush:
            dsc.flush()
            return None

        return dsc.astext()

    @abstractmethod
    def from_file(self, pfile, fformat="xyz"):
        """Import Points or Polygons from a file (deprecated).

        Supported import formats (fformat):

        * 'xyz' or 'poi' or 'pol': Simple XYZ format

        * 'zmap': ZMAP line format as exported from RMS (e.g. fault lines)

        * 'rms_attr': RMS points formats with attributes (extra columns)

        * 'guess': Try to choose file format based on extension

        Args:
            pfile (str): Name of file or pathlib.Path instance
            fformat (str): File format, see list above

        Returns:
            Object instance (needed optionally)

        Raises:
            OSError: if file is not present or wrong permissions.

        .. deprecated:: 2.16
           Use e.g. xtgeo.points_from_file()
        """
        ...

    @abstractmethod
    def from_list(self, plist):
        """Create Points or Polygons from a list-like input (deprecated).

        This method is deprecated in favor of using e.g. xtgeo.Points(plist)
        or xtgeo.Polygons(plist) instead.

        The following inputs are possible:

        * List of tuples [(x1, y1, z1, <id1>), (x2, y2, z2, <id2>), ...].
        * List of lists  [[x1, y1, z1, <id1>], [x2, y2, z2, <id2>], ...].
        * List of numpy arrays  [nparr1, nparr2, ...] where nparr1 is first row.
        * A numpy array with shape [??1, ??2] ...
        * An existing pandas dataframe

        It is currently not much error checking that lists/tuples are consistent, e.g.
        if there always is either 3 or 4 elements per tuple, or that 4 number is
        an integer.

        Args:
            plist (str): List of tuples, each tuple is length 3 or 4.

        Raises:
            ValueError: If something is wrong with input

        .. versionadded:: 2.6
        .. versionchanged:: 2.16
        .. deprecated:: 2.16
           Use e.g. xtgeo.Points(list_like).
        """
        ...

    def protected_columns(self):
        """
        Returns:
            Columns not deleted by :meth:`delete_columns`, for
            instance the coordinate columns.
        """
        return [self.xname, self.yname, self.zname]

    def delete_columns(self, clist, strict=False):
        """Delete one or more columns by name in a safe way for Points or Polygons.

        Note that the columns returned by :meth:`protected_columns(self)` (for
        instance, the coordinate columns) will not be deleted.

        Args:
            self (obj): Points or Polygons
            clist (list): Name of columns
            strict (bool): I False, will not trigger exception if a column is not
                found. Otherways a ValueError will be raised.

        Raises:
            ValueError: If strict is True and columnname not present

        Example::
            mypoly.delete_columns(["WELL_ID", mypoly.hname, mypoly.dhname])

        .. versionadded:: 2.1
        """
        for cname in clist:
            if cname in self.protected_columns():
                xtg.warnuser(
                    f"The column {cname} is protected and will not be deleted."
                )
                continue

            if cname not in self.dataframe:
                if strict:
                    raise ValueError(f"The column {cname} is not present.")
                else:
                    xtg.warnuser(f"Trying to delete {cname}, but it is not present.")
            else:
                self.dataframe.drop(cname, axis=1, inplace=True)
