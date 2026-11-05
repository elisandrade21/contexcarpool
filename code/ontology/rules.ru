# Reasoning rules R1-R8 as SPARQL 1.1 Update operations (W3C Recommendation).
# R1-R4 infer the comfort level from the available passenger seats ?d; R5-R8
# infer a cost-versus-booking-convenience trade-off from the booking mode and
# the within-search cost score ?k in [0,10] (explanation-level, not scored).
# Each firing is recorded with the qualified PROV-O pattern:
#   firing  a prov:Activity, used the offer, prov:qualifiedAssociation ->
#           prov:Association (prov:agent wm:Reasoner, prov:hadPlan wm:Rk);
#   fact    a prov:Entity, prov:wasGeneratedBy the firing,
#           prov:wasDerivedFrom the offer, rdf:value = inferred individual.
# Node IRIs are derived from the offer IRI, so any SPARQL 1.1 engine produces
# the same graph (checked with Apache Jena ARQ and Python rdflib).

PREFIX wm:   <http://example.org/ridesharing#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
INSERT {
  ?a wm:hasComfortLevel wm:VeryComfortable .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R1 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:VeryComfortable .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasSeatsAvailable ?d . FILTER(?d >= 4)
  BIND(IRI(CONCAT(STR(?a), "-R1-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R1-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R1-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasComfortLevel wm:Comfortable .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R2 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:Comfortable .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasSeatsAvailable ?d . FILTER(?d = 3)
  BIND(IRI(CONCAT(STR(?a), "-R2-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R2-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R2-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasComfortLevel wm:Bearable .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R3 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:Bearable .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasSeatsAvailable ?d . FILTER(?d = 2)
  BIND(IRI(CONCAT(STR(?a), "-R3-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R3-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R3-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasComfortLevel wm:Uncomfortable .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R4 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:Uncomfortable .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasSeatsAvailable ?d . FILTER(?d <= 1)
  BIND(IRI(CONCAT(STR(?a), "-R4-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R4-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R4-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasTradeOff wm:InstantBargain .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R5 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:InstantBargain .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasBookingMode "auto" ; wm:hasCostScore ?k . FILTER(?k >= 7.5)
  BIND(IRI(CONCAT(STR(?a), "-R5-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R5-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R5-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasTradeOff wm:ApprovalBargain .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R6 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:ApprovalBargain .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasBookingMode "manual" ; wm:hasCostScore ?k . FILTER(?k >= 7.5)
  BIND(IRI(CONCAT(STR(?a), "-R6-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R6-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R6-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasTradeOff wm:ConveniencePremium .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R7 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:ConveniencePremium .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasBookingMode "auto" ; wm:hasCostScore ?k . FILTER(?k < 2.5)
  BIND(IRI(CONCAT(STR(?a), "-R7-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R7-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R7-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasTradeOff wm:ApprovalPremium .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R8 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a ; rdf:value wm:ApprovalPremium .
}
WHERE {
  ?a a wm:Travel . ?a wm:hasBookingMode "manual" ; wm:hasCostScore ?k . FILTER(?k < 2.5)
  BIND(IRI(CONCAT(STR(?a), "-R8-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R8-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R8-fact")) AS ?e)
}
