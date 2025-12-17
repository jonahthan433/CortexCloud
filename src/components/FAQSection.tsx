import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const FAQSection = () => {
  const faqs = [
    {
      question: 'What business problems can CortexCloud solve on day one?',
      answer: 'CortexCloud can immediately handle customer support inquiries, appointment scheduling, lead qualification, order processing, and FAQ responses. Our AI agents are pre-trained to understand common business workflows and can be customized to your specific needs within hours.',
    },
    {
      question: 'How fast can CortexCloud deploy voice or WhatsApp agent?',
      answer: 'Most deployments take 24-48 hours. Our team works with you to configure the agent, integrate with your existing systems, and ensure everything is working smoothly before going live. Complex integrations may take up to a week.',
    },
    {
      question: 'Which integrations do CortexCloud agents support?',
      answer: 'We support a wide range of integrations including WhatsApp Business API, Slack, Microsoft Teams, Salesforce, HubSpot, Zendesk, Calendly, Google Calendar, and many more. We also offer custom API integrations for your specific tools.',
    },
    {
      question: "What is CortexCloud's pricing model?",
      answer: 'We offer flexible pricing based on usage and features. Our plans start with a base monthly fee plus per-conversation pricing. This ensures you only pay for what you use while having access to all our powerful features. Contact us for a custom quote.',
    },
    {
      question: 'Will this really be worth it for my business?',
      answer: 'Our clients typically see ROI within the first month. With 24/7 availability, instant responses, and the ability to handle multiple conversations simultaneously, our AI agents can reduce operational costs by up to 70% while improving customer satisfaction scores.',
    },
  ];

  return (
    <section className="py-20 md:py-32 relative">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center mb-12 md:mb-16">
          <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
            FAQ
          </span>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold font-display">
            Frequently asked <span className="text-gradient">questions</span>
          </h2>
        </div>

        {/* FAQ Accordion */}
        <div className="max-w-3xl mx-auto">
          <Accordion type="single" collapsible className="space-y-4">
            {faqs.map((faq, index) => (
              <AccordionItem
                key={index}
                value={`item-${index}`}
                className="glass-strong rounded-xl px-6 border-none"
              >
                <AccordionTrigger className="text-left font-semibold text-foreground hover:text-primary transition-colors py-6">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-muted-foreground pb-6">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  );
};

export default FAQSection;
