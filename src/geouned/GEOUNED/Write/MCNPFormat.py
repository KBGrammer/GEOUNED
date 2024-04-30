##############################
# Module to write MCNP input #
##############################
import math
from datetime import datetime

import FreeCAD

from ..CodeVersion import *
from ..Utils.BasicFunctions_part1 import isOposite, pointsToCoeffs
from ..Utils.Functions import SurfacesDict
from ..Utils.Options.Classes import Options as opt
from .Functions import CardLine, MCNPSurface, changeSurfSign, writeMCNPCellDef


class McnpInput:
    def __init__(self, Meta, Surfaces, setting):
        self.Title = setting["title"]
        self.VolSDEF = setting["volSDEF"]
        self.VolCARD = setting["volCARD"]
        self.U0CARD = setting["UCARD"]
        self.dummyMat = setting["dummyMat"]
        self.Cells = Meta
        self.Options = {
            "Volume": self.VolCARD,
            "Particle": ("n", "p"),
            "Universe": self.U0CARD,
        }
        self.part = "P"

        self.StepFile = setting["stepFile"]
        if isinstance(self.StepFile, (tuple, list)):
            self.StepFile = "; ".join(self.StepFile)

        if self.Title == "":
            self.Title = self.StepFile

        self.__getSurfaceTable__()
        self.__simplifyPlanes__(Surfaces)

        self.Surfaces = self.__sortedSurfaces__(Surfaces)
        self.Materials = set()

        return

    def setSDEF(self, data):

        if data[0] is not None:
            sphereId = data[0][0]
            radius = data[0][1]
            wgt = math.pi * radius * radius * 1e-2
            sdef = "SDEF PAR={} NRM=-1 SUR={} WGT={:13.7e} DIR=d1\n".format(
                self.part, sphereId, wgt
            )
            SI1 = "SI1 0 1\n"
            SP1 = "SP1 -21 1\n"
            self.SDEF_sphere = (sdef, SI1, SP1)
        else:
            self.SDEF_sphere = None
        xmin, xmax, ymin, ymax, zmin, zmax = data[1]

        sdef = f"SDEF PAR={self.part} X=D1 Y=D2 Z=D3 \n"
        SI1 = f"SI1 {xmin * 0.1:13.7e} {xmax * 0.1:13.7e} \n"
        SI2 = f"SI2 {ymin * 0.1:13.7e} {ymax * 0.1:13.7e} \n"
        SI3 = f"SI3 {zmin * 0.1:13.7e} {zmax * 0.1:13.7e} \n"
        SP1 = "SP1 0  1 \n"
        SP2 = "SP2 0  1 \n"
        SP3 = "SP3 0  1 \n"
        self.SDEF_box = (sdef, SI1, SI2, SI3, SP1, SP2, SP3)

    def writeInput(self, filename):
        print(f"write MCNP file {filename}")
        self.inpfile = open(filename, "w", encoding="utf-8")
        self.__write_header__(filename)
        self.__write_cell_block__()
        self.inpfile.write(" \n")

        surfaceHeader = """\
C ##########################################################
C                  SURFACE DEFINITION
C ##########################################################
"""
        self.inpfile.write(surfaceHeader)
        self.__write_surface_block__()
        self.inpfile.write(" \n")

        self.__write_source_block__()

        self.inpfile.close()
        return

    def __write_header__(self, fileout):

        version = GEOUNED_Version
        releaseDate = GEOUNED_ReleaseDate
        freeCAD_Version = "{V[0]:}.{V[1]:}.{V[2]:}".format(V=FreeCAD.Version())

        Header = f"""{self.Title}
C   ______ _______  _____      _     _ __   _ _______ ______  
C  |  ____ |______ |     | ___ |     | | \\  | |______ |     \\ 
C  |_____| |______ |_____|     |_____| |  \\_| |______ |_____/
C Version : {version}     {releaseDate}
C FreeCAD Version : {freeCAD_Version} 
"""

        Information = f"""C
C *************************************************************
C Original Step file : {self.StepFile}
C
C Creation Date : {datetime.now()}
C Solid Cells   : {self.__solidCells__}
C Total Cells   : {self.__cells__}
C Surfaces      : {len(self.Surfaces)}
C Materials     : {len(self.__materials__)}
C
C **************************************************************
"""
        self.inpfile.write(Header)
        self.inpfile.write(Information)
        return

    def __write_cell_block__(self):

        for i, cell in enumerate(self.Cells):
            self.__write_cells__(cell)
        return

    def __write_surface_block__(self):

        for surf in self.Surfaces:
            self.__write_surfaces__(surf)

    def __write_cells__(self, cell):

        index = cell.label

        # if index is None objet not contain cell definition
        # but a comment to insert between cells
        if cell.__id__ is None:
            comment = self.__commentLine__(cell.Comments)
            self.inpfile.write(comment)
            return

        if cell.Material == 0:
            cellHeader = f"{index:<5d} {0:<5d}  "
        else:
            self.Materials.add(cell.Material)
            if abs(cell.Density) < 1e-2:
                cellHeader = f"{index:<5d} {cell.Material:<5d} {cell.Density:11.4e} "
            else:
                cellHeader = f"{index:<5d} {cell.Material:<5d} {cell.Density:11.7f} "

        mcnpcell = "{}{}\n{}{}".format(
            cellHeader,
            self.__cellFormat__(cell.Definition, offset=len(cellHeader)),
            self.__optionFormat__(cell),
            self.__commentFormat__(cell.Comments, cell.MatInfo),
        )
        self.inpfile.write(mcnpcell)
        return

    def __write_surfaces__(self, surface):
        """Write the surfaces in MCNP format"""

        MCNP_def = MCNPSurface(surface.Index, surface.Type, surface.Surf)
        if MCNP_def:
            MCNP_def += "\n"
            self.inpfile.write(MCNP_def)
        else:
            print(f"Surface {surface.Type} cannot be written in MCNP input")
        return

    def __write_source_block__(self):

        if self.SDEF_sphere is None:
            return

        MODE = f"MODE {self.part}\nVOID \nNPS 1e6\n"
        if self.dummyMat:
            mat = list(self.Materials)
            mat.sort()
            MATCARD = ""
            for m in mat:
                MATCARD += f"M{m:<6d} 1001 1\n"
            Block = MATCARD + "C \n" + MODE
        else:
            Block = MODE

        if self.VolSDEF:
            Block += "PRDMP 2J -1\n"
            for line in self.SDEF_box:
                Block += "C " + line
            for line in self.SDEF_sphere:
                Block += line

            celList, volList = self.__get_solidCellVolume__()

            F4Tally = CardLine(f"F4:{self.part} ")
            F4Tally.extend(celList)
            SD4 = CardLine("SD4  ", fmt="13.7e")
            SD4.extend(volList)

            Block += F4Tally.str + "\n"
            if not self.VolCARD:
                Block += SD4.str
            else:
                Block += "C Cell volume normalization is set in cell cards VOL\n"
        else:
            for line in self.SDEF_sphere:
                Block += "C " + line
            for line in self.SDEF_box:
                Block += line

        self.inpfile.write(Block)

    def __cellFormat__(self, Definition, offset=11):
        return writeMCNPCellDef(Definition, tabspace=11, offset=offset)

    def __optionFormat__(self, cell):

        option = ""
        if self.Options["Volume"]:
            if not cell.Void:
                option = f"{'':11s}Vol={cell.Volume * 0.001:e}\n"
            else:
                option = f"{'':11s}Vol=1.0\n"

        option += f"{'':11s}"
        for p in self.Options["Particle"]:
            if cell.MatInfo == "Graveyard":
                option += f"imp:{p}=0     "
            else:
                option += f"imp:{p}=1.0   "

        if self.Options["Universe"] is not None:
            option += f"U={self.Options['Universe']}  "
        option += "\n"

        return option

    def __commentFormat__(self, cComment, mComment=None):

        comment = ""
        if mComment:
            mComment = mComment.split("\n")
            for c in mComment:
                if c:
                    comment += f"{'':11s}${c}\n"

        if cComment.strip() != "":
            cComment = cComment.strip().split("\n")
            for c in cComment:
                if c:
                    comment += f"{'':11s}${c}\n"
        return comment

    def __commentLine__(self, lineComment):
        lineComment = lineComment.strip().split("\n")
        comment = ""
        if lineComment:
            comment = "C \n"
            for c in lineComment:
                if c:
                    comment += f"C {c}\n"
            comment += "C \n"
        return comment

    def __getSurfaceTable__(self):
        self.surfaceTable = {}
        self.__solidCells__ = 0
        self.__cells__ = 0
        self.__materials__ = set()

        for i, CellObj in enumerate(self.Cells):
            if CellObj.__id__ is None:
                continue
            self.__cells__ += 1
            if CellObj.Material != 0:
                self.__materials__.add(CellObj.Material)

            surf = CellObj.Definition.getSurfacesNumbers()
            if not CellObj.Void:
                self.__solidCells__ += 1
            for index in surf:
                if index in self.surfaceTable.keys():
                    self.surfaceTable[index].add(i)
                else:
                    self.surfaceTable[index] = {i}
        return

    def __simplifyPlanes__(self, Surfaces):

        for p in Surfaces["PX"]:
            if p.Surf.Axis[0] < 0:
                p.Surf.Axis = FreeCAD.Vector(1, 0, 0)
                self.__changeSurfSign__(p)

        for p in Surfaces["PY"]:
            if p.Surf.Axis[1] < 0:
                p.Surf.Axis = FreeCAD.Vector(0, 1, 0)
                self.__changeSurfSign__(p)

        for p in Surfaces["PZ"]:
            if p.Surf.Axis[2] < 0:
                p.Surf.Axis = FreeCAD.Vector(0, 0, 1)
                self.__changeSurfSign__(p)

        if opt.prnt3PPlane:
            for p in Surfaces["P"]:
                if p.Surf.pointDef:
                    axis, d = pointsToCoeffs(p.Surf.Points)
                    if isOposite(axis, p.Surf.Axis):
                        self.__changeSurfSign__(p)

        return

    def __sortedSurfaces__(self, Surfaces):
        temp = SurfacesDict(Surfaces)
        surfList = []
        for ind in range(
            Surfaces.IndexOffset, Surfaces.surfaceNumber + Surfaces.IndexOffset
        ):
            s = temp.getSurface(ind + 1)
            if s is not None:
                surfList.append(s)
                temp.delSurface(ind + 1)
        return surfList

    def __changeSurfSign__(self, p):

        if p.Index not in self.surfaceTable.keys():
            print(
                f"{p.Type} Surface {p.Index} not used in cell definition)",
                p.Surf.Axis,
                p.Surf.Position,
            )
            return

        for ic in self.surfaceTable[p.Index]:
            surf = self.Cells[ic].Definition.getSurfacesNumbers()
            for s in surf:
                if s == p.Index:
                    changeSurfSign(s, self.Cells[ic].Definition)

    def __get_solidCellVolume__(self):

        solidList = []
        volumeList = []
        for m in self.Cells:
            if m.CellType == "solid" and m.__id__ is not None:
                solidList.append(m.label)
                volumeList.append(m.Volume * 1e-3)

        return solidList, volumeList
