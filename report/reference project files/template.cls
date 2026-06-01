\LoadClass[a4paper,12pt]{article}

\RequirePackage{silence}
\WarningFilter{fancyhdr}{\headheight is too small}
\WarningFilter{fancyhdr}{\footskip is too small}

%--------------------------------------

%\RequirePackage[french]{babel}
\RequirePackage[utf8]{inputenc}
\RequirePackage[section]{placeins}
\RequirePackage[T1]{fontenc}
\RequirePackage{xcolor}
\RequirePackage{biblatex}
\RequirePackage{ragged2e}
\RequirePackage{lipsum}
\RequirePackage{array}
\RequirePackage{booktabs}
\RequirePackage{amsmath} 
\RequirePackage{siunitx}
\RequirePackage{enumitem}
\RequirePackage{float}
\RequirePackage{graphicx}
\RequirePackage[justification=centering]{caption}
\RequirePackage{subcaption}
\RequirePackage{tikz}
\RequirePackage{tikzpagenodes}
\usetikzlibrary{calc}
\RequirePackage{fancyhdr}
\RequirePackage{url}
\RequirePackage[hidelinks]{hyperref}
\RequirePackage{geometry}
\geometry{left=2.5cm, right=2.5cm, top=2cm, bottom=5.5cm}
\RequirePackage{siunitx} 
\RequirePackage{tabularx}
\RequirePackage{microtype} 
\RequirePackage{pgfplots}
\RequirePackage{minted}
\RequirePackage[most, minted, breakable, skins, theorems]{tcolorbox}
\RequirePackage{csquotes}
\RequirePackage{eurosym}
\RequirePackage{svg}
\RequirePackage{amssymb}
\RequirePackage{amsthm}
\RequirePackage{environ}
\RequirePackage{etoolbox}
\RequirePackage{seqsplit}
\RequirePackage{xparse}
\pgfplotsset{compat=1.18}
\RequirePackage{hyperref}
% \hypersetup{
%     colorlinks=true,
%     linkcolor=blue,
%     filecolor=magenta,      
%     urlcolor=cyan,
%     pdftitle={DFT},
%     pdfpagemode=FullScreen,
% }
%--------------------------------------

\definecolor{centrale_red}{RGB}{178,33,51} % Rouge centralien
\definecolor{rwth_blue}{RGB}{0, 84, 159}

\newlength{\blasonYshift}
\setlength{\blasonYshift}{-3cm}
\newlength{\logoYshift}
\setlength{\logoYshift}{3.1cm}

%--------------------------------------

\sisetup{output-decimal-marker = {,}} % Séparateur décimal
\renewcommand{\headrulewidth}{0pt} % Retirer le trait de séparation de l'en-tête
\setlength{\footskip}{4cm}  % Augmente la distance entre le texte et le pied de page
\setlist[itemize]{label=\textbullet} % Définit la puce par défaut pour les itemize.
\setlist[itemize,2]{label=\textbf{--}}   % Définit la puce par défaut pour les deuxièmes niveaux d'itemize.

%--------------------------------------

\newcommand{\enseignant}[1]{\renewcommand{\enseignant}{#1}}
\newcommand{\eleves}[1]{\renewcommand{\eleves}{#1}}
\newcommand{\titre}[1]{\renewcommand{\titre}{#1}}
\newcommand{\soustitre}[1]{\renewcommand{\soustitre}{#1}}

%--------------------------------------

% Header et Footer
\pagestyle{fancy}
\fancyheadoffset{1cm}
\setlength{\headheight}{2.5cm}
\fancyhf{}

\fancyhead[L]{%
  \begin{tikzpicture}[remember picture,overlay]
    \node[inner sep=0pt, anchor=north west]
      at ([yshift=\logoYshift]current page text area.north west)
      {\includesvg[height=1.2 cm]{logos/rwth.svg}};
  \end{tikzpicture}%
}

\lfoot{\raisebox{-0.75cm}{\hspace{-8.5cm}\includegraphics[height=4cm]{logos/motif_blue.png}}}

\newcommand{\fairepagedegarde}{
    \rfoot{} % Retirer le numéro de page de la page de garde
    \begin{centering}
    
        \vspace*{3cm}
        
        {\Huge \textbf{\textcolor{rwth_blue}{\titre}} \par}
        
        \vspace{1cm}
        
        {\Large \textbf{\soustitre} \par}
    
        \vspace{3cm}
        
        \begin{minipage}{0.4\textwidth}
                \begin{flushleft} \medium
                    \emph{\textbf{Name:}}\\ 
                    \eleves
                \end{flushleft}
            \end{minipage}
            ~
            \begin{minipage}{0.4\textwidth}
                \begin{flushright} \medium
                    \emph{\textbf{Matriculation No:}}\\
                    \enseignant
                \end{flushright}
            \end{minipage}
        
        \vfill
        
        {\small \today \par}
        
    \end{centering}
    \newpage
    
    \setcounter{page}{1}  
    \fancyfoot[R]{%
        \begin{tikzpicture}[remember picture,overlay]
            \node[inner sep=0pt,anchor=south east] (crest)
                at ([yshift=\blasonYshift]current page text area.south east)
                {\includegraphics[height=1.5cm]{logos/blason_blue.png}};
            \node[text=white,font=\bfseries] at (crest.center) {\thepage};
        \end{tikzpicture}%
    }
}

%--------------------------------------

% Table des matières
\newcommand{\fairetabledesmatieres}{
    \tableofcontents
    \newpage
}

%--------------------------------------

% Insérer une figure
\newcommand{\insererfigure}[4]{
    \begin{figure}[H]
        \centering
        \includegraphics[width=#2]{#1}
        \caption{#3}
        \label{fig:#4}
    \end{figure}
}

%--------------------------------------

% Insérer une bibliographie
\newcommand{\insererbiblio}{
    \newpage
    \section{Bibliographie}
    \newrefcontext[sorting=none]
    \printbibliography[heading=none]
    \newpage
}

%--------------------------------------

% Style des boîtes de code
\newtcblisting[auto counter]{codebox}[3][]{%
  enhanced,
  breakable,
  listing engine=minted,
  listing only,
  minted language=#3,
  minted options={
    fontsize=\small,
    breaklines,
    numbers=none,
    autogobble
  },
  title={
    \begin{tabular}{@{}m{0.80\linewidth}m{0.18\linewidth}@{}}
      {\bfseries\sffamily{Code \thetcbcounter~: #2}} & \raggedleft \texttt{\small #3}
    \end{tabular}
  },
  label=#1,
  colback=rwth_blue!7,
  colframe=rwth_blue,
  fonttitle=\color{white},
  coltitle=white,
  boxrule=1.5pt,
  arc=2mm,
}


%--------------------------------------

% Définit un flag pour indiquer si nous sommes dans du code ou non
\newif\ifgenericboxresumed
\genericboxresumedfalse

% Définir genericenvironment
\NewDocumentCommand{\genericenvironment}{O{Problème} m m}{%
  \begin{tcolorbox}[
    enhanced,
    breakable,
    colback = white,
    colbacktitle = rwth_blue!0,
    coltitle = rwth_blue,
    boxrule = 0pt,
    frame hidden,
    borderline west = {0.5mm}{0.0mm}{rwth_blue},
    fonttitle = \bfseries\sffamily,
    before skip = 3ex,
    after skip = 3ex,
    title = {\ifgenericboxresumed\else#1~#2\ifstrempty{#3}{}{~: #3}\fi},
    parbox=false,
    before upper={%
        \setlength{\parindent}{2em}%
        \setlength{\parskip}{1ex plus 0.5ex minus 0.2ex}%  
    },
  ]
}
\NewDocumentCommand{\endgenericenvironment}{}{%
  \end{tcolorbox}
}

% Pour stocker les valeurs d'affichage des références
\newcommand{\genericboxreftext}[2]{%
  \expandafter\gdef\csname genericboxreftext@#1\endcsname{#2}%
}

% Redéfinir \@setref pour utiliser les valeurs stockées si disponibles
\makeatletter
\let\original@setref\@setref
\def\@setref#1#2#3{%
  \ifcsname genericboxreftext@#3\endcsname
    \hyperref[#3]{\csname genericboxreftext@#3\endcsname}%
  \else
    \original@setref{#1}{#2}{#3}%
  \fi
}
\makeatother

% Commande pour suspendre genericbox
\NewDocumentCommand{\pausegenericbox}{}{%
  \endgenericenvironment
}

% Commande pour reprendre genericbox sans afficher l'en-tête
\NewDocumentCommand{\resumegenericbox}{}{%
  \genericboxresumedtrue
  \genericenvironment[\currentgenericboxtype]{\currentgenericboxnumber}{\currentgenericboxdesc}%
}

% Modifier genericbox pour stocker ses paramètres et réinitialiser le flag
\NewDocumentEnvironment{genericbox}{O{Problème} m m}{%
  \genericboxresumedfalse % Réinitialiser le flag au début
  \gdef\currentgenericboxtype{#1}%
  \gdef\currentgenericboxnumber{#2}%
  \gdef\currentgenericboxdesc{#3}%
  \genericenvironment[#1]{#2}{#3}%
  \edef\generic@label{#1-\detokenize{#2}}%
  \phantomsection % Crée une ancre pour hyperref
  \label{\generic@label}%
  \genericboxreftext{\generic@label}{#2}%
}{%
  \endgenericenvironment
}