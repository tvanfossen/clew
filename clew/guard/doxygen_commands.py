# SPDX-License-Identifier: MIT
"""Doxygen's built-in special commands: tags the gate recognises but does not enforce (PG7; 2.0.0).

FOUND BY A CONSUMER (the entropic session, on its first gate run over header doc blocks): `@p`,
`@c`, `@code` and `@endcode` were reported as unknown tags, with hints such as "did you mean
@pre?". They are doxygen commands. The gate's known set listed about 25 of them and missed the
inline formatting commands that API documentation in headers uses most.

THE LIST IS DOXYGEN'S OWN, from the manual's "Special Commands" chapter (doxygen 1.9/1.10),
spelled without the leading `@` or `\\`. Symbol commands (`\\f$`, `\\f[`, `\\&` ...) are left
out: the gate's tag reader only sees `@word` names. A command missing here is reported as
unknown, which is the safe direction: the reader can list it under `guard.validate.extra_tags`.

@brief Doxygen's built-in command names.
@version 1
"""

from __future__ import annotations

## Every word-shaped doxygen special command.
DOXYGEN_COMMANDS: frozenset[str] = frozenset(
    """
    a addindex addtogroup anchor arg attention author authors b brief bug c callergraph callgraph
    category cite class code collaborationgraph concept cond copybrief copydetails copydoc
    copyright date def defgroup deprecated details diafile dir directorygraph docbookinclude
    docbookonly dontinclude dot dotfile doxyconfig e else elseif em emoji endcode endcond
    enddocbookonly enddot endhtmlonly endif endinternal endlatexonly endlink endmanonly endmsc
    endparblock endrtfonly endsecreflist enduml endverbatim endxmlonly enum example exception
    extends file fileinfo fn groupgraph headerfile hidecallergraph hidecallgraph
    hidecollaborationgraph hidedirectorygraph hideenumvalues hidegroupgraph hideincludedbygraph
    hideincludegraph hideinheritancegraph hideinitializer hiderefby hiderefs htmlinclude htmlonly
    idlexcept if ifnot image implements important include includedbygraph includedoc
    includegraph includelineno ingroup inheritancegraph interface internal invariant
    latexinclude latexonly li line lineinfo link mainpage maninclude manonly memberof module msc
    mscfile n name namespace noop nosubgrouping note overload p package page par paragraph param
    parblock post pre private privatesection property protected protectedsection protocol public
    publicsection pure qualifier raisewarning ref refitem related relatedalso relates
    relatesalso remark remarks result return returns retval rtfinclude rtfonly sa secreflist
    section see short showdate showenumvalues showinitializer showrefby showrefs since skip
    skipline snippet snippetdoc snippetlineno static startuml struct subpage subsection
    subsubsection tableofcontents test throw throws todo tparam typedef union until var verbatim
    verbinclude version vhdlflow warning weakgroup xmlinclude xmlonly xrefitem
    """.split()
)
