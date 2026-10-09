"""Literal figure from nineteen existing, independently checked bank-specific rows."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'crossbank/crossbank-pressure.json'
def main():
    data=json.loads(SOURCE.read_text());rows=data['rows']
    slots=[];headers=[];y=14
    for bank,heading in [('original96','Original 96-case bank'),('matched96','Matched 96-case bank'),('popular96','Popular-model 96-case bank'),('shared312','Shared 312-case bank')]:
        headers.append((y,heading));y-=1
        configs=list(dict.fromkeys(r['configuration_label'] for r in rows if r['bank_id']==bank))
        for config in configs:slots.append((y,bank,config));y-=1
    assert len(slots)==11
    parts=[r'\begin{tikzpicture}']
    inventory=[]
    for panel,representation in enumerate(('raw','supplied')):
        yticks=','.join(str(s[0]) for s in slots)
        labels=','.join('{'+s[2]+'}' for s in slots) if panel==0 else ','.join('' for s in slots)
        title='Raw parameters' if representation=='raw' else 'Supplied expected costs'
        parts.append(r'\begin{axis}['+f'name=forest{panel},at={{({panel*6.1:.2f}cm,0cm)}},anchor=south west,width=5.5cm,height=8.1cm,scale only axis,xmin=-15,xmax=105,ymin=-.65,ymax=14.7,xtick={{0,25,50,75,100}},ytick={{{yticks}}},yticklabels={{{labels}}},'+r'tick label style={font=\scriptsize},title style={font=\small},xlabel style={font=\scriptsize},axis x line*=bottom,axis y line*=left,xmajorgrids,grid style={black!10},tick align=outside,clip=false,title={'+title+r'},xlabel={Increase in inferior-report choices (pp)}]')
        parts.append(r'\draw[black!45,dashed,line width=.4pt] (axis cs:0,-.45)--(axis cs:0,14.5);')
        for y,bank,config in slots:
            matches=[r for r in rows if r['bank_id']==bank and r['configuration_label']==config and r['representation']==representation]
            if not matches:
                assert bank=='shared312' and representation=='raw'
                parts.append(f'\\node[font=\\scriptsize,text=black!55] at (axis cs:43,{y}) {{Not evaluated}};');continue
            r=matches[0];lo=r['identification_lower_pp'];hi=r['identification_upper_pp'];point=r['mean_percentage_points'];ci=r['simultaneous_ci_lower_pp'] is not None
            if ci:
                cl=r['simultaneous_ci_lower_pp'];ch=r['simultaneous_ci_upper_pp']
                parts.extend([f'\\draw[black,line width=.45pt] (axis cs:{cl:.12f},{y})--(axis cs:{ch:.12f},{y});',f'\\draw[black,line width=.45pt] (axis cs:{cl:.12f},{y-.085:.3f})--(axis cs:{cl:.12f},{y+.085:.3f});',f'\\draw[black,line width=.45pt] (axis cs:{ch:.12f},{y-.085:.3f})--(axis cs:{ch:.12f},{y+.085:.3f});'])
            parts.append(f'\\draw[black,line width=2.0pt] (axis cs:{lo:.12f},{y})--(axis cs:{hi:.12f},{y});')
            mark='*'
            marker_option='' if ci else ',mark options={fill=white}'
            parts.append(f'\\addplot[only marks,mark={mark},mark size=1.65pt,color=black{marker_option}] coordinates {{({point:.12f},{y})}};')
            note=f'{r["complete_cases"]}/{r["planned_cases"]} '+(r['inference_family'] if ci else 'CI not reported')
            parts.append(f'\\node[font=\\tiny,anchor=east,inner sep=0pt] at (axis cs:102,{y-.35:.3f}) {{{note}}};')
            inventory.append({'bank_id':bank,'configuration_label':config,'representation':representation,'y':y,'point_pp':point,'identification_bounds_pp':[lo,hi],'native_simultaneous_ci_pp':[r['simultaneous_ci_lower_pp'],r['simultaneous_ci_upper_pp']] if ci else None,'native_family':r['inference_family'],'complete_cases':r['complete_cases'],'planned_cases':r['planned_cases'],'valid_pairs':r['valid_pairs'],'planned_pairs':r['planned_pairs']})
        if panel==0:
            for y,label in headers:parts.append(f'\\node[font=\\scriptsize,anchor=west] at (axis cs:-15,{y}) {{{label}}};')
        else:
            for y,label in headers:parts.append(f'\\draw[black!18,line width=.3pt] (axis cs:-15,{y-.35:.2f})--(axis cs:105,{y-.35:.2f});')
        parts.append(r'\end{axis}')
    parts.extend([r'\node[font=\scriptsize,align=center,anchor=north] at ([yshift=-1.12cm]forest0.south east) {Filled dots: simultaneous 95\% CI (thin). Hollow dots: CI not reported.\\Thick segments: full-plan missing-outcome bounds. Labels: complete / planned cases.};',r'\end{tikzpicture}'])
    body='\n'.join(parts)+'\n'
    caption=r'Bank-specific endorsement contrasts, without pooling cases or configurations. Older banks compare strong inferior endorsement with neutral prompts; the shared bank compares the inferior bundle with its second neutral repeat. Raw and supplied-cost tasks are distinct. Dots retain the original complete-case estimates and weighting; thick segments retain all planned missing outcomes. Thin intervals are the existing Holm10, Holm5 or Holm9 simultaneous 95\% intervals under independent whole-case clusters; hollow points mark contrasts for which a confidence interval was not reported. Full denominators and settings are supplied in the companion.'
    inline=r'\begin{figure*}[t]\centering'+'\n'+r'\resizebox{\textwidth}{!}{%'+'\n'+body+'}\n'+r'\caption{'+caption+'}\n'+r'\label{fig:cross-bank}'+'\n'+r'\end{figure*}'+'\n'
    (HERE/'cross-bank-inline.tex').write_text(inline)
    (HERE/'cross-bank.tex').write_text(inline)
    standalone=r'''\documentclass[10pt,border=6pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{graphicx,pgfplots,capt-of}
\pgfplotsset{compat=1.18}
\begin{document}\setcounter{figure}{2}
\begin{minipage}{7in}\centering
\resizebox{\textwidth}{!}{%
'''+body+'}\n'+r'\captionof{figure}{'+caption+'}\n'+r'\end{minipage}\end{document}'+'\n'
    (HERE/'cross-bank-standalone.tex').write_text(standalone)
    (HERE/'forest-figure-inputs.json').write_text(json.dumps({'crossbank_input_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'plotted_rows':inventory,'caption_latex':caption,'main_omits_incomplete_retired_stages':True,'new_inference':False,'slots_without_raw_measurement':3},indent=2,sort_keys=True)+'\n')
    print('ACTUAL_CROSS_BANK_FIGURE_SOURCE_PASS: 19 existing contrasts, 11 bank/configuration slots, no new inference')
if __name__=='__main__':main()
