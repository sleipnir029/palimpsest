\LoadClass[a4paper,11pt]{article}

%--------------------------------------

\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern} % scalable fonts (needed for microtype expansion on BasicTeX)
\RequirePackage{xcolor}
\RequirePackage{ragged2e}
\RequirePackage{array}
\RequirePackage{booktabs}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{siunitx}
\RequirePackage{enumitem}
\RequirePackage{float}
\RequirePackage{graphicx}
\RequirePackage[justification=justified,font=footnotesize,labelfont=bf,skip=4pt]{caption}
\RequirePackage{subcaption}
\RequirePackage{tikz}
\RequirePackage{tikzpagenodes}
\usetikzlibrary{calc}
\RequirePackage{fancyhdr}
\RequirePackage{url}
\RequirePackage{geometry}
\geometry{left=3.5cm, right=3.5cm, top=2cm, bottom=4cm, footskip=2.5cm}
\RequirePackage{tabularx}
\RequirePackage{longtable}
\RequirePackage{microtype}
\RequirePackage{parskip} % block paragraphs: no indent, half-line gap (patches lists/TOC)
\RequirePackage{listings}
\RequirePackage[most, breakable, skins, theorems]{tcolorbox}
\RequirePackage{eurosym}
\RequirePackage{etoolbox}
\RequirePackage[hidelinks]{hyperref}

% Allow long URLs in the references to break anywhere (no xurl on BasicTeX)
\makeatletter
\g@addto@macro\UrlBreaks{\do\a\do\b\do\c\do\d\do\e\do\f\do\g\do\h\do\i\do\j%
  \do\k\do\l\do\m\do\n\do\o\do\p\do\q\do\r\do\s\do\t\do\u\do\v\do\w\do\x\do\y\do\z%
  \do\A\do\B\do\C\do\D\do\E\do\F\do\G\do\H\do\I\do\J\do\K\do\L\do\M\do\N\do\O%
  \do\P\do\Q\do\R\do\S\do\T\do\U\do\V\do\W\do\X\do\Y\do\Z\do\.\do\-\do\_}
\makeatother
\Urlmuskip=0mu plus 1mu\relax

%--------------------------------------

\definecolor{rwth_blue}{RGB}{0, 84, 159}

\newlength{\blasonYshift}
\setlength{\blasonYshift}{-2.2cm}
\newlength{\logoYshift}
\setlength{\logoYshift}{3.1cm}

%--------------------------------------

\renewcommand{\headrulewidth}{0pt} % no header rule
\setlength{\footskip}{2.5cm}
\setlength{\parskip}{0.6\baselineskip plus 2pt minus 1pt}
\setlength{\emergencystretch}{3em} % avoid rare overfull lines on the narrower measure
\setlist[itemize]{label=\textbullet}
\setlist[itemize,2]{label=\textbf{--}}
\setlist{topsep=2pt, itemsep=2pt, parsep=0pt} % keep lists tight under the new \parskip

%--------------------------------------

\newcommand{\enseignant}[1]{\renewcommand{\enseignant}{#1}}
\newcommand{\eleves}[1]{\renewcommand{\eleves}{#1}}
\newcommand{\titre}[1]{\renewcommand{\titre}{#1}}
\newcommand{\soustitre}[1]{\renewcommand{\soustitre}{#1}}
\newcommand{\datevar}[1]{\renewcommand{\datevar}{#1}}

%--------------------------------------

% Header and footer
\pagestyle{fancy}
\fancyheadoffset{1cm}
\setlength{\headheight}{2.5cm}
\fancyhf{}

\fancyhead[L]{%
  \begin{tikzpicture}[remember picture,overlay]
    \node[inner sep=0pt, anchor=north west]
      at ([yshift=\logoYshift]current page text area.north west)
      {\includegraphics[height=1.2cm]{logos/rwth.png}};
  \end{tikzpicture}%
}


\newcommand{\fairepagedegarde}{
    \rfoot{} % no page number on cover
    \begin{centering}

        \vspace*{3cm}

        {\LARGE \textbf{\textcolor{rwth_blue}{\titre}} \par}

        \vspace{1cm}

        {\Large \textbf{\soustitre} \par}

        \vspace{3cm}

        \begin{minipage}{0.4\textwidth}
                \begin{flushleft} \large
                    \emph{\textbf{Name:}}\\
                    \eleves
                \end{flushleft}
            \end{minipage}
            ~
            \begin{minipage}{0.4\textwidth}
                \begin{flushright} \large
                    \emph{\textbf{Matriculation No:}}\\
                    \enseignant
                \end{flushright}
            \end{minipage}

        \vfill

        {\small \datevar \par}

    \end{centering}
    \newpage

    \setcounter{page}{1}
    \fancyfoot[R]{%
        \begin{tikzpicture}[remember picture,overlay]
            \node[inner sep=0pt,anchor=south east] (crest)
                at ([yshift=\blasonYshift]current page text area.south east)
                {\includegraphics[height=0.9cm]{logos/blason_blue.png}};
            \node[text=white,font=\footnotesize\bfseries] at ([yshift=0.16cm]crest.center) {\thepage};
        \end{tikzpicture}%
    }
}

%--------------------------------------

% Table of contents
\newcommand{\fairetabledesmatieres}{
    \tableofcontents
    \newpage
}

%--------------------------------------

% Code box: tcolorbox + listings (no minted, no shell-escape)
\lstdefinestyle{rwthcode}{
  basicstyle=\footnotesize\ttfamily,
  breaklines=true,
  columns=fullflexible,
  keepspaces=true,
  showstringspaces=false,
  numbers=none,
  upquote=true,
}

\newtcblisting[auto counter]{codebox}[3][]{%
  enhanced,
  listing only,
  listing style=rwthcode,
  title={%
    \begin{tabular}{@{}m{0.80\linewidth}m{0.16\linewidth}@{}}
      {\bfseries\sffamily Code \thetcbcounter~: #2} & \raggedleft \texttt{\small #3}
    \end{tabular}%
  },
  label=#1,
  colback=rwth_blue!7,
  colframe=rwth_blue,
  fonttitle=\color{white},
  coltitle=white,
  boxrule=1.5pt,
  arc=2mm,
}
