import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import FadeIn from './FadeIn';

const FAQSection = () => {
  const faqs = [
    {
      question: 'What business problems can CortexCloud solve on day one?',
      answer: 'CortexCloud can immediately handle customer support inquiries, appointment scheduling, lead qualification, order processing, and FAQ responses. Our AI agents are pre-trained to understand common business workflows and can be customized to your specific needs within hours.',
    },
    {
      question: 'How fast can CortexCloud deploy voice or WhatsApp agent?',
      answer: 'Most deployments take 24-48 hours. Our team works with you to configure the agent, integrate with your existing systems, and ensure everything is working smoothly before going live.',
    },
    {
      question: 'Which integrations do CortexCloud agents support?',
      answer: 'We support a wide range of integrations including WhatsApp Business API, Slack, Microsoft Teams, Salesforce, HubSpot, Zendesk, Calendly, Google Calendar, and many more.',
    },
    {
      question: "What is CortexCloud's pricing model?",
      answer: 'We offer flexible pricing based on usage and features. Our plans start with a base monthly fee plus per-conversation pricing. Contact us for a custom quote.',
    },
    {
      question: 'Will this really be worth it for my business?',
      answer: 'Our clients typically see ROI within the first month. With 24/7 availability and instant responses, our AI agents can reduce operational costs by up to 70% while improving customer satisfaction.',
    },
  ];

  return (
    <section className="py-16 md:py-32 relative">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <FadeIn>
          <div className="text-center mb-8 md:mb-16">
            <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
              FAQ
            </span>
            <h2 className="text-mobile-title lg:text-5xl font-bold font-display">
              Frequently asked <span className="text-gradient">questions</span>
            </h2>
          </div>
        </FadeIn>

        {/* FAQ Accordion */}
        <div className="max-w-3xl mx-auto">
          <Accordion type="single" collapsible className="space-y-3 md:space-y-4">
            {faqs.map((faq, index) => (
              <FadeIn key={index} delay={index * 0.1}>
                <AccordionItem
                  value={`item-${index}`}
                  className="glass-strong rounded-xl px-4 md:px-6 border-none"
                >
                  <AccordionTrigger className="text-left font-semibold text-foreground hover:text-primary transition-colors py-4 md:py-6 text-sm md:text-base">
                    {faq.question}
                  </AccordionTrigger>
                  <AccordionContent className="text-muted-foreground pb-4 md:pb-6 text-sm md:text-base">
                    {faq.answer}
                  </AccordionContent>
                </AccordionItem>
              </FadeIn>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  );
};

export default FAQSection;
