"""Literal grayscale figure sources from existing audited arms; no inference."""
import json,hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
DATA=HERE.parent/'diagnostics/actual/synthesis-diagnostics.json'
MODELS=['llama_default','deepseek_off','luna_off']
TITLES={MODELS[0]:r'Llama 4 Maverick\\ default',MODELS[1]:r'DeepSeek v4 Pro\\ reasoning off',MODELS[2]:r'GPT-5.6 Luna\\ reasoning off'}

def figure(arms,conditions,labels,name,caption,height):
    n=len(conditions);parts=[r'\begin{tikzpicture}']
    for m,model in enumerate(MODELS):
        ticklabels=','.join('{'+x+'}' for x in labels) if m==0 else ','.join('' for _ in labels)
        parts.append(r'\begin{axis}['+f'name=panel{m},at={{({m*4.45:.2f}cm,0cm)}},anchor=south west,width=3.85cm,height={height}cm,scale only axis,xmin=-3,xmax=103,ymin=.4,ymax={n+.5},xtick={{0,25,50,75,100}},ytick={{'+','.join(str(x) for x in range(n,0,-1))+'},yticklabels={'+ticklabels+r'},tick label style={font=\scriptsize},title style={font=\small,align=center},xlabel style={font=\scriptsize},axis x line*=bottom,axis y line*=left,xmajorgrids,grid style={black!10},tick align=outside,clip=false,title={'+TITLES[model]+r'},xlabel={Inferior-report choices (\%)}]')
        for y,condition in zip(range(n,0,-1),conditions):
            a=next(x for x in arms if x['model_id']==model and x['condition']==condition)
            lo,hi=[100*x for x in a['full_plan_identification_bounds']];dot=100*a['observed_rate']
            parts.extend([f'\\draw[black,line width=.65pt] (axis cs:{lo:.12f},{y})--(axis cs:{hi:.12f},{y});',
                          f'\\draw[black,line width=.65pt] (axis cs:{lo:.12f},{y-.07:.3f})--(axis cs:{lo:.12f},{y+.07:.3f});',
                          f'\\draw[black,line width=.65pt] (axis cs:{hi:.12f},{y-.07:.3f})--(axis cs:{hi:.12f},{y+.07:.3f});',
                          f'\\addplot[only marks,mark=*,mark size=1.6pt,color=black] coordinates {{({dot:.12f},{y})}};',
                          f'\\node[font=\\scriptsize,anchor=north,inner sep=0pt] at (axis cs:50,{y-.13:.3f}) {{{a["count"]}/{a["valid"]} errors}};'])
        parts.append(r'\end{axis}')
    parts.extend([r'\node[font=\scriptsize,anchor=north] at ([yshift=-1.12cm]panel1.south) {Dots: errors / valid choices. Whiskers: all-planned missing-outcome bounds.};',r'\end{tikzpicture}'])
    body='\n'.join(parts)+'\n'
    inline=r'\begin{figure*}[t]\centering'+'\n'+r'\resizebox{\textwidth}{!}{%'+'\n'+body+'}\n'+r'\caption{'+caption+'}\n'+r'\label{fig:'+name+'}\n'+r'\end{figure*}'+'\n'
    (HERE/(name+'-inline.tex')).write_text(inline)
    alias='choices-priority' if name=='endorsement-rates' else 'cue-components'
    wrapped=inline.replace('fig:endorsement-rates','fig:choices-priority').replace('fig:wording-components','fig:cue-components')
    (HERE/(alias+'.tex')).write_text(wrapped)
    standalone=r'''\documentclass[10pt,border=6pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath,graphicx,pgfplots,capt-of}
\pgfplotsset{compat=1.18}
\setlength{\emergencystretch}{1.5em}
\makeatletter\newlabel{fig:endorsement-rates}{{2}{}}\makeatother
\begin{document}
'''+('\\setcounter{figure}{1}\n' if name=='endorsement-rates' else '\\setcounter{figure}{3}\n')+r'''
\begin{minipage}{7in}\centering
\resizebox{\textwidth}{!}{%
'''+body+'}\n'+r'\captionof{figure}{'+caption+'}\n'+r'\end{minipage}\end{document}'+'\n'
    (HERE/(name+'.tex')).write_text(standalone)
    return {'figure':name,'conditions':conditions,'configurations':MODELS,'all_planned_per_arm':624,'caption_latex':caption,'inline_source_sha256':hashlib.sha256(inline.encode()).hexdigest()}

def main():
    data=json.loads(DATA.read_text());arms=data['all_arm_error_rates']
    a=figure(arms,['neutral_2','bundle_bad','bundle_good','guard_neutral','guard_bundle_bad'],
             ['Neutral','Inferior bundle','Optimal bundle','Priority neutral','Priority inferior'],
             'endorsement-rates',r'Choice changes under bundled endorsement and the identical cost-priority sentence, on the shared 312-case bank. Each row plans 624 choices (two orders per case); labels give observed errors/valid choices. Dots are the proportion choosing the inferior total-cost report. Tiny whiskers assign every unavailable choice both possible outcomes using the full planned denominator, not a confidence interval. In inferior-target rows this proportion is endorsement following; in the optimal-target row following equals one minus the error rate. Neutral rows have no endorsed target. The two priority rows provide the matched neutral and inferior-endorsement comparison.',4.8)
    c=figure(arms,['neutral_2','bundle_bad','sponsor_bad','commitment_bad','preference_bad_1','preference_bad_2'],
             ['Neutral','Bundled cue','Sponsor only','Commitment only','Preference wording 1','Preference wording 2'],
             'wording-components',r'Wording-associated error rates on the same 312-case bank. Each row plans 624 choices; labels give observed errors/valid choices. Dots and tiny whiskers use the same valid-response rates and full-plan missingness bounds as Figure~\ref{fig:endorsement-rates}. GPT-5.6 Luna has low errors under the bundled cue but many under sponsor-only and the first preference wording. Sponsor-only, commitment-only and both preference wordings endorse the inferior report; they lack optimal-target counterparts. These are distinct observed conditions, not additive component effects or an isolated internal mechanism.',5.8)
    (HERE/'rates-figure-inputs.json').write_text(json.dumps({'actual_data_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),'figures':[a,c],'arm_rows':arms,'new_inference':False},indent=2,sort_keys=True)+'\n')
    print('ACTUAL_RATES_FIGURE_SOURCE_PASS: 15 endorsement rows and 18 wording rows, no new inference')

if __name__=='__main__':main()
