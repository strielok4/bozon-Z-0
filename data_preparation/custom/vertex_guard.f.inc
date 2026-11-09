      REASON=0
      LPVA=0
C Guard applies to both automatic refits and high-p recovery refits.
C LQ(PA+1) is the reconstructed mother vertex, not an MC association.
      IF (LVECP(ITK).GT.0) THEN
         LPVA=LQ(LVECP(ITK)+1)
         IF (LPVA.GT.0) THEN
            IF (JBIT(IQ(LPVA),2).NE.0.OR.
     +          JBIT(IQ(LPVA),3).NE.0) THEN
               REASON=1
            ENDIF
         ENDIF
      ENDIF
C Mirror PSHSCT impact cuts BEFORE refit can move a track to the PV.
C No new numerical cuts; preserve PSHSCT primary/beamspot convention.
      IPXY=QTRAC(38,ITK)
      IPZ=QTRAC(39,ITK)
      IF (KVTX(16,1).GT.0) THEN
         CALL VFILL(VCOVG,6,0.)
         CALL VFILL(DCAG,4,-999.)
         CALL TBDCAE(QTRAC(4,ITK),XYZBS,VCOVG,DCAG)
         IPXY=DCAG(1)
         IPZ=DCAG(2)
      ENDIF
      STH=0.
      IF (VECP(6,ITK).GT.0.) THEN
         STH=SQRT(MAX(0.,1.-(VECP(3,ITK)/VECP(6,ITK))**2))
      ENDIF
      IF (ABS(IPXY).GT.TRKRPH(ICUT)) REASON=REASON+2
      IF (ABS(IPZ)*STH.GT.TRKZET(ICUT)) REASON=REASON+4
      IF (REASON.NE.0) THEN
         WRITE(*,*) 'AUD PVREFIT ',IIIRUN,IIIEVT,ITK,
     +        1,REASON,VECP(4,ITK),IPXY,IPZ
         RETURN
      ENDIF
