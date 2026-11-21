import json,numpy as np
from shapely.geometry import LineString,Point
def tangent_fit(P):
    c=P.mean(0); u,s,vt=np.linalg.svd(P-c); d=vt[0]
    res=np.abs((P-c)@vt[1]).max()
    return c,d,res
def corner(ln,s,A0=10,A1=28,STR=0.8):
    """arms: arc length s-A1..s-A0 and s+A0..s+A1 on the line. returns implied fillet radius etc or None"""
    if s-A1<0 or s+A1>ln.length: return None
    a=np.array([ln.interpolate(t).coords[0] for t in np.arange(s-A1,s-A0+.1,1.0)])
    b=np.array([ln.interpolate(t).coords[0] for t in np.arange(s+A0,s+A1+.1,1.0)])
    ca,da,ra=tangent_fit(a); cb,db,rb=tangent_fit(b)
    if ra>STR or rb>STR: return dict(bad='arm not straight',ra=round(ra,1),rb=round(rb,1))
    # orient: a direction forward, b direction forward
    if da@(a[-1]-a[0])<0: da=-da
    if db@(b[-1]-b[0])<0: db=-db
    th=np.degrees(np.arccos(np.clip(da@db,-1,1)))  # deflection
    if th<40: return dict(bad='turn small',th=round(th,0))
    M=np.array([[da[0],-db[0]],[da[1],-db[1]]])
    try: t=np.linalg.solve(M,cb-ca)
    except Exception: return None
    Pt=ca+da*t[0]
    # sanity: P ahead of arm a and behind arm b
    if t[0]<0 or t[1]>0: return dict(bad='arms diverge',th=round(th,0))
    # line apex: point on the corner stretch nearest to P
    seg=np.array([ln.interpolate(x).coords[0] for x in np.arange(s-A0,s+A0+.1,0.5)])
    g=np.hypot(*(seg-Pt).T).min()
    k=1/np.cos(np.radians(th/2))-1
    r=g/k
    # side: does corner stretch lie inside the angle (toward the arms' inner side)? use max dist of seg from P
    return dict(th=round(th,0),g=round(g,1),r=round(r,1),ra=round(ra,1),rb=round(rb,1),
                inner=float(np.hypot(*(seg-Pt).T).max()))
